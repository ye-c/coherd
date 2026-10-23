"""coherd.push — feedback/notify 共用核心逻辑（消息自描述标记注入 + 送达 + 精简审计）。

把 peer 间发消息的"回执义务"变成消息自描述标记：CLI 派生 role/type 注入 `[<role>|<type>]: ` 前缀
（type=feedback/notify，命令名即标记名），接收端一读即知是否需回执，不依赖后台守护进程（watch 已废弃）。

职责：
  1. 派生自身 role / ws / peer role
  2. 校验 peer 名（fail-open：拿不到 agent 列表就不校验，拿到则不在列表即拒）
  3. 注入 `[<role>|<type>]: ` 标记前缀（agent 只写 body 正文，不手写前缀）
  4. O_APPEND 向 session events.log 追一行精简审计 JSON {ws,from,to,type,msg_id,ts,body}
     （无 session 目录时回退全局 DEFAULT_LOG 兜底；body = 未经标记前缀的原始正文）
  5. 调 `herdr agent prompt <peer-agent> "<msg>"` 送达
落地顺序：日志先行，再送达 —— 送达失败不丢审计行。
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from .client import agent_list
from .tracker import CONFIG_HOME, glob_session_dir

# 全局事件日志（冷启动兜底）：有 session 目录（任意内容）时事件落 session/events.log，
# 仅真无 session 目录回退此处（防每次 push 自建空目录）。DEFAULT_LOG 不能删。
DEFAULT_LOG = CONFIG_HOME / "events.log"

# 送达执行器签名（可注入以便测试替换真实 herdr 调用）
Sender = Callable[[str, str], bool]
# peer 名单提供器签名：list[str] = 权威名单；None = 无法判定（fail-open、不校验）
PeerListFn = Callable[[], list[str] | None]


def ws_from_env() -> str | None:
    """从 env 派生 ws 短号（HERDR_WORKSPACE_ID 小写），无则 None。"""
    raw = os.environ.get("HERDR_WORKSPACE_ID")
    return raw.lower() if raw else None


def derive_role(agent_name: str, ws: str) -> str:
    """agent 名去 `${ws}-` 前缀取 role；无前缀则原样（libero/standalone 兜底）。"""
    prefix = f"{ws}-"
    return agent_name.removeprefix(prefix)


def _self_role_from_pane_list() -> str | None:
    """末级 fallback：agent.list 按 HERDR_PANE_ID 查自身 name。

    集群 pane 内 launcher 不注入 COHERD_ROLE/HERDR_AGENT_NAME（bin/coherd §6），
    故回退到 herdr 权威源 agent.list（复用 watch 已验证的 name+pane_id 链路）：
    返回匹配 pane 的 agent name（如 `w2t-reviewer`），由 run() 再 derive_role。
    无 pane/socket env 或未命中（libero/standalone）返回 None。
    """
    pane = os.environ.get("HERDR_PANE_ID")
    sock = os.environ.get("HERDR_SOCKET_PATH")
    if not (pane and sock):
        return None
    for a in agent_list(sock):
        if a.get("pane_id") == pane:
            return a.get("name")
    return None


def known_peers() -> list[str] | None:
    """默认 peer 名单：herdr agent.list 的 name 列表；无 socket / 失败 / 空 → None（不校验）。

    fail-open 是故意：standalone / libero / 测试 / socket 抖动都拿不到名单，
    把"拿不到"当"没这个人"会把正常发送全炸掉。
    """
    sock = os.environ.get("HERDR_SOCKET_PATH")
    if not sock:
        return None
    try:
        agents = agent_list(sock)
    except Exception:  # noqa: BLE001 — 任何异常都等于无法判定，走 fail-open
        return None
    names = [a.get("name") for a in agents if isinstance(a, dict) and a.get("name")]
    return names or None


def make_msg_id() -> str:
    """唯一 msg_id：纳秒时间戳 + uuid 短段，保证并发不撞。"""
    return f"{time.time_ns()}-{uuid.uuid4().hex[:8]}"


def make_event(
    ws: str,
    from_: str,
    to: str,
    msg_id: str,
    ts: str | None = None,
    msg_type: str = "feedback",
    body: str = "",
) -> dict:
    """事件日志条目 dict（字段序 ws,from,to,type,msg_id,ts,body，type=feedback/notify）。"""
    return {
        "ws": ws,
        "from": from_,
        "to": to,
        "type": msg_type,  # feedback(待回执) / notify(单向)，命令名即标记名
        "msg_id": msg_id,
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "body": body,  # 未经标记前缀的原始消息正文（原文追溯）
    }


def event_line(event: dict) -> str:
    """事件 dict → 单行 JSON（ensure_ascii=False 保中文明文）。"""
    return json.dumps(event, ensure_ascii=False)


def append_event(log_path: Path, line: str) -> None:
    """O_APPEND 追加单行（POSIX append 模式对小写原子，免锁并发安全）。"""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def send_prompt(peer_agent: str, msg: str) -> bool:
    """默认送达器：`herdr agent prompt <peer> "<msg>"`。失败返回 False。"""
    try:
        proc = subprocess.run(
            ["herdr", "agent", "prompt", peer_agent, msg],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


def run(
    peer_agent: str,
    msg: str,
    *,
    ws: str | None = None,
    role: str | None = None,
    log_path: Path | None = None,
    sender: Sender = send_prompt,
    self_role_fn: Callable[[], str | None] | None = None,
    peer_list_fn: PeerListFn | None = None,
    msg_type: str = "feedback",
) -> dict:
    """push 主流程：① 派生（env → 显参 → 报错）② 校验 peer ③ 注入标记 ④ 精简审计 ⑤ 送达。

    - 标记：`[<role>|<type>]: <body>`（type=feedback/notify，CLI 注入，agent 只写 body）。
    - peer 校验：拿不到名单（None）放行；拿到且 peer 不在其中 → 拒发且不写日志。
    - 日志先行：append 成功即审计完成，后续送达失败不丢行。
    - 返回含 from/to/type/msg_id/ts/delivered/line，供调用方回显与测试断言。
    """
    if not peer_agent or not msg:
        raise ValueError("peer 与消息均不可为空")

    # 前缀拒绝（机制防线）：marker 是 CLI 私有注入物，agent 只写 body。正文以
    # `[<role>|feedback]: ` / `[<role>|notify]: ` / `[<role>]: ` 开头 → 视为 agent
    # 自造前缀，拒绝并交还调用方（防重复如 `[x|feedback]: [x|feedback]: ...`）。
    import re as _re

    if _re.match(r"^\s*\[\w+(?:\|\w+)?\]:", msg):
        stripped = _re.sub(r"^\s*\[\w+(?:\|\w+)?\]:\s*", "", msg, count=1)
        raise ValueError(
            "消息正文应以 body 开头，勿手写 `[<role>|<type>]: ` 前缀（CLI 自动注入）。"
            f" 已剥离前缀后的正文：{stripped!r}"
        )

    # ① 派生 ws / role / peer role
    resolved_ws = ws or ws_from_env()
    if not resolved_ws:
        raise ValueError("无法派生 ws：未提供 --ws 且 HERDR_WORKSPACE_ID 未设置")

    resolved_role = role or os.environ.get("COHERD_ROLE")
    if not resolved_role:
        owner = os.environ.get("HERDR_AGENT_NAME")
        if owner:
            resolved_role = derive_role(owner, resolved_ws)
    if not resolved_role:
        name = (self_role_fn or _self_role_from_pane_list)()
        if name:
            resolved_role = derive_role(name, resolved_ws)
    if not resolved_role:
        raise ValueError(
            "无法派生 role：未提供 --role，且 COHERD_ROLE / HERDR_AGENT_NAME / agent.list 均缺"
        )

    peer_role = derive_role(peer_agent, resolved_ws)

    # ② peer 名校验（fail-open）：发往 user/@用户/NOBODY 这类非 agent 名的消息会被
    # `herdr agent prompt` 静默失败（sender 只把失败折成 False），消息只落进日志里。
    # 只有确实拿到非空名单才判定；拒发发生在写日志之前，审计不被垃圾污染。
    known = (peer_list_fn or known_peers)()
    if known and peer_agent not in known:  # 空名单 = 无人可知 → 放行
        raise ValueError(
            f"未知 peer agent: {peer_agent!r}（不在 herdr agent list 中）"
            " — 用 `herdr agent list` 查全名（形如 w2p-reviewer），本次未发送也未记账"
        )

    # ③ 注入 `[<role>|<type>]: ` 标记前缀（类型=feedback/notify，命令名即标记名）
    signed_msg = f"[{resolved_role}|{msg_type}]: {msg}"

    # ④ 精简审计（O_APPEND，日志先行：type 标识消息类型，无后台待回执登记）
    event = make_event(
        resolved_ws,
        resolved_role,
        peer_role,
        make_msg_id(),
        msg_type=msg_type,
        body=msg,
    )
    line = event_line(event)
    # 日志路径：显式 log_path 优先；无则 per-session（有 session 目录 → 落
    # session/events.log），冷启动无 session 目录 → 回退全局 DEFAULT_LOG 兜底（防每次自建空目录）。
    session = glob_session_dir(resolved_ws)
    path = log_path or ((session / "events.log") if session else DEFAULT_LOG)
    append_event(path, line)

    # ⑤ 送达注入标记后的消息（失败不丢审计行，返回 delivered=False）
    delivered = sender(peer_agent, signed_msg)

    return {
        "ws": resolved_ws,
        "from": resolved_role,
        "to": peer_role,
        "type": msg_type,
        "peer_agent": peer_agent,
        "msg_id": event["msg_id"],
        "ts": event["ts"],
        "delivered": delivered,
        "log_path": str(path),
        "line": line,
    }