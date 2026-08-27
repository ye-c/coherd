"""coherd.watch — coherd watch 单例断链兜底 watcher（T-B，spec §5/§6/§8）。

把「靠自觉 push」换成「运行时兜底 + 超限升级到人」：订阅 herdr socket 的
`pane.agent_status_changed` 事件，重放 `push-events.log` 维护账本
`pending[ws][receiver]=sender`，idle ∧ pending 未清 → 提醒；幂等去重；连续 2 次
未清 → escalate（coordinator / 用户）。

设计拆分（便于单测）：
- `Ledger`：账本重放（offset 续读）+ 反向清账，纯数据逻辑，可注入日志路径。
- `decide`：idle 判定纯函数（幂等 / 节流 / escalate），可注入 now 与 throttle。
- `Watch`：socket 读线程 → 有界队列 → 单 consumer 的编排壳（socket 可注入 mock）。

遵守 spec §8 不变量 1-4：
  1. push 不依赖 watcher 存活 —— 本模块只读账本，不写 push 路径。
  2. 同一 pane 同一 pending 最多提醒 2 次，之后必 escalate。
  3. offset/账本续读由 Ledger 持久化（重启不丢）。
  4. 不改 herdr 源码、不侵入 agent 循环，只调既有 socket API + `herdr agent prompt`。
"""

from __future__ import annotations

import json
import os
import queue
import socket
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .tracker import CONFIG_HOME

# 事件常量
EVENT_STATUS_CHANGED = "pane.agent_status_changed"
IDLE = "idle"

# 默认账本文件（可被 COHERD_CONFIG_HOME 覆盖，测试隔离）
PUSH_LOG = CONFIG_HOME / "push-events.log"
# 状态（offset 续读 + pid 锁）落盘
STATE_FILE = CONFIG_HOME / "watch-state.json"
PID_FILE = CONFIG_HOME / "watch.pid"

# 升级阈值：提醒次数达此即 escalate（不变量 2）
ESCALATE_AT = 2
# 节流：同 pane 相邻提醒最小间隔（防 send_prompt timeout=30 阻塞堆积，备注 2）
THROTTLE_SECONDS = 5.0
# 有界事件队列容量（spec §5.4）
QUEUE_MAX = 1024

# 判定动作
SKIP = "skip"
REMIND = "remind"
ESCALATE = "escalate"

# 默认提醒/升级消息模板（含具体动作，spec §5.3）
REMIND_TMPL = "你对 [{sender}] 有未回执，立即 `coherd push {sender} ...` 回复。"
ESCALATE_TMPL = (
    "[watch] {receiver} 对 {sender} 连续 2 次 idle 未回执（断链），转入人工。"
)


# ---------------------------------------------------------------------------
# 账本（L）
# ---------------------------------------------------------------------------
@dataclass
class Ledger:
    """push-events.log 重放账本：pending[(ws, receiver)] = sender。

    - offset 记录已重放到日志的字节位置，重启从 offset 续读（spec §8 不变量 3）。
    - 每条 `send(from=F, to=T)` 事件说明「F 发消息给 T」→ T 欠 F 回执。
    - 反向清账（D7）：看到 `from==原 sender 且 to==原 receiver` 的消息，
      表示原 receiver 已主动回执 → 清 pending。本条自身再登记新欠。
    """

    pending: dict[tuple[str, str], str] = field(default_factory=dict)
    offset: int = 0

    def apply(self, rec: dict) -> None:
        """应用一条账本记录（send 事件），维护欠账 + 反向清账。"""
        op = rec.get("op")
        ws, f, t = rec.get("ws"), rec.get("from"), rec.get("to")
        if op != "send" or not (ws and f and t):
            return
        # 反向清账：F 曾欠 T，现 F 发消息给 T → 已回执
        if self.pending.get((ws, f)) == t:
            del self.pending[(ws, f)]
        # 本消息：T 欠 F
        self.pending[(ws, t)] = f

    def replay(self, log_path: Path, from_offset: int) -> int:
        """从 from_offset 续读日志新行并 apply，返回新的 offset（日志当前大小）。

        offset 语义 = 已读到日志文件末尾的字节位置。重复行 apply 幂等。
        """
        if not log_path.exists():
            return from_offset
        size = log_path.stat().st_size
        if from_offset > size:
            from_offset = 0  # 日志被轮转/截断：从零重放（快照已在关停持久化）
        with open(log_path, "r", encoding="utf-8") as f:
            f.seek(from_offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue  # 半行写入/截断，跳过（O_APPEND 时序）
                self.apply(rec)
        return size

    def owner(self, ws: str, receiver: str) -> str | None:
        """返回 receiver 欠谁的账（无欠账返回 None）。"""
        return self.pending.get((ws, receiver))


def load_state(path: Path = STATE_FILE) -> int:
    """读持久化 offset。无状态文件返回 0。"""
    try:
        with open(path, encoding="utf-8") as f:
            return int(json.load(f).get("offset", 0))
    except (OSError, ValueError, json.JSONDecodeError):
        return 0


def save_state(path: Path, offset: int) -> None:
    """持久化 offset（供重启续读）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"offset": offset}, f)


# ---------------------------------------------------------------------------
# idle 判定（幂等 / 节流 / escalate）—— 纯函数
# ---------------------------------------------------------------------------
def decide(
    owner: str | None,
    count: int,
    last_remind: float,
    now: float,
    throttle: float = THROTTLE_SECONDS,
) -> tuple[str, int, float]:
    """判定一条 idle 事件该做什么。

    - owner=None（无欠账）→ SKIP，状态不变。
    - count==0（未提醒过）→ REMIND，count=1，记 last_remind=now。
    - count>=1 且距上次提醒 < throttle → SKIP（防抖，不重复连发）。
    - count==1 且节流过了 → ESCALATE，count=2（连续 2 次未清，停止循环，不变量 2）。
    - count>=2 → SKIP（已 escalate，幂等不再动该 pane）。

    幂等（D5）：同 pane 已提醒且 pending 未清 → 节流窗口内 SKIP，不重复 warning。
    返回 (action, new_count, new_last_remind)。
    """
    if owner is None:
        return SKIP, count, last_remind
    if count == 0:
        return REMIND, 1, now
    if now < last_remind + throttle:
        return SKIP, count, last_remind
    if count < ESCALATE_AT:
        return ESCALATE, count + 1, now
    return SKIP, count, last_remind




def derive_role(agent_name: str, ws: str) -> str:
    """agent 名去 `${ws}-` 前缀取 role（如 `w2p-reviewer`→`reviewer`）。

    无前缀则原样返回（libero/standalone 场景兜底）。与 push.derive_role 同语义，
    本模块自足避免循环依赖。
    """
    prefix = f"{ws}-"
    return agent_name[len(prefix):] if agent_name.startswith(prefix) else agent_name


def role_from_event(data: dict, ws: str) -> str | None:
    """从 idle 事件 data 提取角色名（agent/display_agent/title 含 `<ws>-<role>`）。

    取最后出现形如 `<ws>-xxx` 的段，返回 xxx 第一个词（去 ws- 前缀）。
    找不到返回 None。
    """
    for key in ("display_agent", "agent", "title"):
        v = data.get(key)
        if not isinstance(v, str):
            continue
        idx = v.rfind(f"{ws}-")
        if idx >= 0:
            return v[idx + len(ws) + 1 :].strip().split()[0]
    return None


# ---------------------------------------------------------------------------
# watcher 编排（socket 读线程 → 有界队列 → 单 consumer）
# ---------------------------------------------------------------------------
@dataclass
class Watch:
    """单例 watcher。socket 与 sender 可注入以便单测 mock。"""

    log_path: Path = PUSH_LOG
    state_path: Path = STATE_FILE
    pid_path: Path = PID_FILE
    ws: str | None = None
    socket_path: str | None = None
    sender: Callable[[str, str], bool] | None = None
    escalate_agent: str | None = None
    throttle: float = THROTTLE_SECONDS
    queue_max: int = QUEUE_MAX
    counts: dict[str, int] = field(default_factory=dict)   # pane -> remind count
    last_remind: dict[str, float] = field(default_factory=dict)
    panes: dict[str, str] = field(default_factory=dict)    # pane_id -> role
    agents: dict[str, str] = field(default_factory=dict)   # pane_id -> agent 全名
    ledger: Ledger = field(default_factory=Ledger)
    stop: bool = False

    def __post_init__(self):
        if self.ws is None:
            self.ws = (os.environ.get("COHERD_WS")
                       or os.environ.get("HERDR_WORKSPACE_ID", "").lower()
                       or "")
        if self.socket_path is None:
            self.socket_path = os.environ.get("HERDR_SOCKET_PATH")
        if self.sender is None:
            from . import push as P

            self.sender = P.send_prompt

    # ---- pid 锁（spec §10 多实例防护）----
    def acquire_pid_lock(self) -> bool:
        """写 pid 锁；若已有存活实例返回 False（拒绝并发第二实例）。"""
        pid_path = self.pid_path
        if pid_path.exists():
            try:
                old = int(pid_path.read_text(encoding="utf-8").strip())
                os.kill(old, 0)  # 0 号信号只探活不杀
                return False  # 已有存活实例
            except (ValueError, ProcessLookupError):
                pass  # 旧 pid 已死/非法 → 覆盖
            except PermissionError:
                return False  # 无法探活，保守拒绝
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(str(os.getpid()), encoding="utf-8")
        return True

    def release_pid_lock(self) -> None:
        try:
            self.pid_path.unlink(missing_ok=True)
        except OSError:
            pass

    # ---- 事件循环 ----
    def run(self) -> int:
        """主循环：replay 账本 → 订阅 socket → 读线程入队 → 单 consumer。"""
        if not self.socket_path:
            raise RuntimeError("HERDR_SOCKET_PATH 未设置，无法订阅 herdr 事件")
        if not self.ws:
            raise RuntimeError("无法派生 ws：未提供 --ws，且 COHERD_WS / HERDR_WORKSPACE_ID 均缺")
        if not self.acquire_pid_lock():
            raise RuntimeError("已有 watch 实例运行（pid 锁占用），拒绝并发第二实例")

        # 账本：从持久化 offset 续读（不变量 3）
        self.ledger.offset = load_state(self.state_path)
        self.ledger.offset = self.ledger.replay(self.log_path, self.ledger.offset)
        save_state(self.state_path, self.ledger.offset)

        sock = self._connect_socket()
        q: queue.Queue = queue.Queue(maxsize=self.queue_max)

        # 读线程：socket 流式读事件 → 入队
        reader = threading.Thread(target=self._read_loop, args=(sock, q), daemon=True)
        reader.start()
        try:
            self._consumer_loop(q)
        finally:
            self.stop = True
            try:
                sock.close()
            except OSError:
                pass
            self.release_pid_lock()
        return 0

        
    def _connect_socket(self):
        """建事件的订阅连接（长连接，读事件流）。

        spec §5.2（coordinator 修订）：pane.agent_status_changed 强制 per-pane，
        无 workspace 粗订阅。故：先经独立短连接 `pane.list` 枚举全部 pane，再在
        本订阅连接发送一条含多 subscriptions（每 pane 一个 agent_status_changed
        + 一条 pane.created 补发现）的 events.subscribe。注：herdr 普通请求为
        请求-响应短连接（响应后服务端关闭），订阅是唯一长连接，故枚举不走本连接。
        """
        panes = self.enum_panes()
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.socket_path)
        subscriptions: list[dict] = [{"type": "pane.created"}]
        for p in panes:
            subscriptions.append({"type": EVENT_STATUS_CHANGED, "pane_id": p})
        req = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "watch_sub",
                "method": "events.subscribe",
                "params": {"subscriptions": subscriptions},
            }
        )
        s.sendall(req.encode("utf-8") + b"\n")
        return s

    def enum_panes(self) -> list[str]:
        """独立短连接调 agent.list 建 pane_id→role 映射，返回全部 pane_id。

        P1 修复（reviewer）：herdr 事件载荷的 agent 字段是 CLI 标签（pi/claude/omp），
        name（w2p-reviewer）只在 agent.list 的 AgentInfo.name。故主路径用 agent.list
        的 name + derive_role 建 self.panes[pane_id]=role / self.agents[pane_id]=全名；
        pane 补发现后也可经此重建。
        """
        if not self.socket_path:
            return []
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.socket_path)
        try:
            req = json.dumps(
                {"jsonrpc": "2.0", "id": "watch_list", "method": "agent.list",
                 "params": {}}
            )
            s.sendall(req.encode("utf-8") + b"\n")
            line = self._recv_full_json(s)
            agents = (line.get("result") or {}).get("agents") or []
            return self.build_pane_map(agents, self.ws or "")
        except Exception:
            return []
        finally:
            try:
                s.close()
            except OSError:
                pass

    def build_pane_map(self, agents: list, ws: str) -> list[str]:
        """纯函数：从 agent.list 的 agents 载荷建映射，返回 pane_id 列表（P1）。

        agents: [{name, pane_id, workspace_id, ...}]；name 如 `w2p-reviewer`。
        建 self.panes[pane_id]=role（去 ${ws}- 前缀）、self.agents[pane_id]=name。
        新 pane 补发现后调此重建映射。
        """
        self.panes = {}
        self.agents = {}
        for a in agents:
            name = a.get("name")
            pane = a.get("pane_id")
            if not (name and pane):
                continue
            self.agents[pane] = name
            self.panes[pane] = derive_role(name, ws or "")
        return list(self.panes.keys())  # 只列成功建映射的 pane（name+pane_id 齐全）

    @staticmethod
    def _recv_full_json(sock) -> dict:
        """读请求-响应短连接的完整 JSON 响应（到 EOF）。"""
        buf = b""
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                break
            buf += chunk
        try:
            return json.loads(buf.split(b"\n", 1)[0])
        except (json.JSONDecodeError, IndexError):
            return {}
    def _read_loop(self, sock, q: queue.Queue) -> None:
        """读线程：逐行解析 socket 事件，入有界队列；队列满则丢弃（限流）。"""
        buf = b""
        while not self.stop:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    try:
                        q.put_nowait(ev)
                    except queue.Full:
                        pass  # consumer 积压：跳过（限流兜底，避免队列无限膨胀）
            except OSError:
                break

    def _consumer_loop(self, q: queue.Queue) -> None:
        """单 consumer：顺序处理事件，保证同 pane 不并发重复 prompt。"""
        while not self.stop:
            try:
                ev = q.get(timeout=0.5)
            except queue.Empty:
                continue
            self._handle_event(ev)

    def _handle_event(self, ev: dict) -> None:
        """处理一条事件：截 idle 转态 → 判定 → 提醒/升级/跳过。"""
        if ev.get("event") != EVENT_STATUS_CHANGED:
            return
        data = ev.get("data") or {}
        if data.get("agent_status") != IDLE:
            return
        ws = data.get("workspace_id", "").lower()
        # 跨 ws 分桶：只处理本 watcher 关注 ws（粗订阅全部，此处过滤）
        if self.ws and ws and ws != self.ws:
            return
        pane = data.get("pane_id", "")
        role = self.panes.get(pane)
        if not role:
            # P1：事件载荷无 role 名（agent=CLI 标签）。新 pane 未入映射 →
            # 重拉 agent.list 重建（pane.created 补发现闭环），再兜底 role_from_event
            self.enum_panes()
            role = self.panes.get(pane) or role_from_event(data, ws or self.ws)
        if not role:
            return
        self.panes[pane] = role

        # replay 增量账本（跨进程 O_APPEND 时序：处理事件前补拉新行，备注 1）
        self.ledger.offset = self.ledger.replay(self.log_path, self.ledger.offset)
        save_state(self.state_path, self.ledger.offset)

        owner = self.ledger.owner(ws or self.ws, role)
        now = time.monotonic()
        action, count, last = decide(
            owner, self.counts.get(pane, 0), self.last_remind.get(pane, 0.0),
            now, self.throttle,
        )
        self.counts[pane] = count
        self.last_remind[pane] = last

        if action == REMIND and owner:
            self._remind(pane, role, owner)
        elif action == ESCALATE and owner:
            self._escalate(pane, role, owner)

    def _remind(self, pane: str, role: str, owner: str) -> None:
        """动作：提醒该 agent 立即回执（含具体动作，spec §5.3）。"""
        peer = self.agents.get(pane)  # 全名（w2p-reviewer），agent.list 建立（P1）
        if not peer:
            peer = f"{self.ws}-{role}" if self.ws else role
        msg = f"[watch] {REMIND_TMPL.format(sender=owner).rstrip()}（pane={pane} idle 未回执）"
        try:
            self.sender(peer, msg)
        except Exception:
            pass  # 提醒失败不致命：账本仍在，下轮事件会再判

    def _escalate(self, pane: str, role: str, owner: str) -> None:
        """动作：升级到 coordinator / 用户（写 stderr 兜底报用户可见）。"""
        target = self.escalate_agent or (f"{self.ws}-coordinator" if self.ws else None)
        msg = ESCALATE_TMPL.format(receiver=role, sender=owner)
        if target:
            try:
                self.sender(target, msg)
            except Exception:
                pass
        print(f"{msg}（pane={pane}）", file=sys.stderr)