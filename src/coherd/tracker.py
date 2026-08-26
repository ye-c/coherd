"""tracker — coherd 任务 tracker 的读写与 YAML frontmatter 手写解析（不依赖 pyyaml）。

body 标准化约定：frontmatter 是权威 schema（9 固定字段，程序读写），frontmatter 之外的
markdown body 为自由上下文（agent 补充），解析器不校验 body。

解析器核心（_parse_frontmatter）≤15 行：按行寻 frontmatter 边界（行首精确 '---'），
逐行 split(': ') 建 dict，支持 `key: |` 块标量（缩进续行拼接）；以行首精确 '---' 判界，
故块内缩进的 '---' 永不误判为边界。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# 存储根（可用 COHERD_CONFIG_HOME 覆盖，测试隔离用）
CONFIG_HOME = Path(os.environ.get("COHERD_CONFIG_HOME", "~/.config/coherd")).expanduser()
TASKS_DIR = CONFIG_HOME / "tasks"
ARCHIVE_DIR = CONFIG_HOME / "archive"

# frontmatter 固定字段顺序（写入即此序）
FIELDS = ("id", "ws", "created_at", "task_name", "status", "parent_id",
          "objective", "dod", "output_path")
STATUSES = ("pending", "active", "done")

# id / ws 作文件名与 id 前缀：正则防注入（阻止路径穿越/特殊字符）
ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _split_blocks(text: str) -> tuple[list[str], str]:
    """按行切 frontmatter 块与正文。边界 = 首行与后继首个行首精确 '---' 的无缩进行。
    块标量续行带 2 空格缩进（见 render_frontmatter），故值内 '---' 永不误判。"""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("非法 tracker: 缺少 '---' 分隔的 frontmatter")
    end = next((i for i in range(1, len(lines)) if lines[i] == "---"), None)
    if end is None:
        raise ValueError("非法 tracker: frontmatter 未闭合（缺结尾 '---'）")
    return lines[1:end], "\n".join(lines[end + 1:])


def _parse_frontmatter(block: list[str]) -> dict[str, str]:
    """手写 frontmatter 解析：逐行 split(': ') 建 dict，支持 `|` 块标量（缩进续行拼接）。"""
    data: dict[str, str] = {}
    key, buf = None, []
    for line in block:
        if key and (line.startswith(" ") or line.startswith("\t")):  # 块标量续行
            buf.append(line.strip())
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if not k or not re.match(r"^[a-zA-Z_]+$", k):
            continue
        if key:
            data[key] = "\n".join(buf)
        key = k
        buf = [] if v == "|" else [v]
    if key:
        data[key] = "\n".join(buf)
    return data


def render_frontmatter(data: dict, body: str = "") -> str:
    """渲染 frontmatter + body。多行字段用 `key: |` 块标量（一致缩进 2 空格）。body 原样附加。"""
    lines = ["---"]
    for f in FIELDS:
        v = data.get(f, "")
        if not isinstance(v, str):
            v = "" if v is None else str(v)
        if "\n" in v:
            lines.append(f"{f}: |")
            lines.extend("  " + ln if ln else "" for ln in v.splitlines())
        else:
            lines.append(f"{f}: {v}")
    lines.append("---")
    if body:
        lines.extend(["", body.rstrip()])
    return "\n".join(lines) + "\n"


def validate(data: dict) -> None:
    """校验必填字段 + 状态枚举 + 字符集。不合法即抛 ValueError。"""
    for f in ("id", "ws", "created_at", "task_name", "status", "objective",
              "dod", "output_path"):
        if not str(data.get(f, "")).strip():
            raise ValueError(f"tracker 缺必填字段: {f}")
    if str(data.get("status", "")) not in STATUSES:
        raise ValueError(f"status 非法: {data.get('status')!r}（需 {STATUSES}）")
    if not ID_RE.match(str(data.get("id", ""))):
        raise ValueError(f"id 含非法字符: {data.get('id')!r}（需 [a-zA-Z0-9_-]）")


def tracker_path(ws: str, task_id: str, base: Path = TASKS_DIR) -> Path:
    """tracker 文件路径：<base>/<ws>/<id>.md。ws 走 ID_RE 防注入。"""
    if not ID_RE.match(ws):
        raise ValueError(f"ws 含非法字符: {ws!r}（需 [a-zA-Z0-9_-]）")
    return base / ws / f"{task_id}.md"


def write_new(data: dict, body: str = "") -> Path:
    """写新 tracker 到 tasks/<ws>/<id>.md。已存在即抛 FileExistsError（查重兜底）。"""
    validate(data)
    p = tracker_path(data["ws"], data["id"])
    if p.exists():
        raise FileExistsError(f"tracker 已存在: {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_frontmatter(data, body), encoding="utf-8")
    return p


def load(track: Path) -> dict:
    """读 tracker 文件 + 解析 frontmatter，附加 _path / _ws / _body。"""
    text = track.read_text(encoding="utf-8")
    block, body = _split_blocks(text)
    data = _parse_frontmatter(block)
    data["_body"] = body.strip()
    data["_path"] = str(track)
    data["_ws"] = track.parent.name
    return data


def find_tracker(task_id: str) -> dict:
    """按 id 跨 ws 查 tracker（show/archive/status 用，不知 ws 时）。不存在抛 FileNotFoundError。"""
    if not ID_RE.match(task_id):
        raise FileNotFoundError(f"非法 task id: {task_id!r}")
    if not TASKS_DIR.is_dir():
        raise FileNotFoundError(f"tracker 不存在: {task_id}（tasks 目录为空）")
    for ws_dir in sorted(TASKS_DIR.iterdir()):
        if not ws_dir.is_dir():
            continue
        p = ws_dir / f"{task_id}.md"
        if p.is_file():
            return load(p)
    raise FileNotFoundError(f"tracker 不存在: {task_id}")


def set_status(task_id: str, status: str, body: str = "") -> None:
    """更新 tracker 状态落 frontmatter（保留原 body）。非法 status / ID 不存在均抛错。"""
    if status not in STATUSES:
        raise ValueError(f"status 非法: {status!r}（需 {STATUSES}）")
    data = find_tracker(task_id)
    data["status"] = status
    Path(data["_path"]).write_text(
        render_frontmatter(data, body if body else data.get("_body", "")),
        encoding="utf-8")