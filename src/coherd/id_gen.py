"""id_gen — tracker id 生成与查重。

格式 <ws>-<YYYYMMDD>-<序号>：同 ws 同日自 001 递增。id 直接作文件名，
因此 ws 走 ID_RE 正则校验（[a-zA-Z0-9_-]）防注入；序号按已有文件扫描去顶防重复。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from .tracker import ID_RE, TASKS_DIR

_SEQ_RE = re.compile(r"^[A-Za-z0-9_-]+-\d{8}-(\d{3})\.md$")


def next_id(ws: str, now: datetime | None = None) -> str:
    """生成新 id：<ws>-<UTC 日>-<同日最大序号+1>。"""
    if not ID_RE.match(ws):
        raise ValueError(f"ws 含非法字符: {ws!r}（需 [a-zA-Z0-9_-]）")
    now = now or datetime.now(timezone.utc)
    date = now.strftime("%Y%m%d")
    seqs = _existing_seq(ws, date)
    n = (max(seqs) + 1) if seqs else 1
    return f"{ws}-{date}-{n:03d}"


def _existing_seq(ws: str, date: str) -> set[int]:
    """同一 ws 同日已有 tracker 的序号集合（扫描文件名，查重防碰撞）。"""
    ws_dir = Path(TASKS_DIR) / ws
    if not ws_dir.is_dir():
        return set()
    seqs: set[int] = set()
    for p in ws_dir.glob(f"{ws}-{date}-*.md"):
        m = _SEQ_RE.match(p.name)
        if m:
            seqs.add(int(m.group(1)))
    return seqs