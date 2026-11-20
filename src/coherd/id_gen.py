"""id_gen — tracker id 生成。

格式 <ws>-<YYYYMMDDHHMMSS>-<NN>（ws + 14 位 UTC 秒时间戳 + 2位序号）。
用户拍板：id 唯一性由秒级时间戳与递增序号保证，同 ws 同秒重复创建递增重试。
ws 走 ID_RE 正则校验（[a-zA-Z0-9_-]）防注入。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .tracker import ID_RE

# id 秒段：14 位精确数字（YYYYMMDDHHMMSS）
_TS_RE = re.compile(r"^\d{14}$")


def next_id(ws: str, now: datetime | None = None, seq: int = 1) -> str:
    """生成新 id：<ws>-<UTC 秒时间戳 YYYYMMDDHHMMSS>-<NN>。"""
    if not ID_RE.match(ws):
        raise ValueError(f"ws 含非法字符: {ws!r}（需 [a-zA-Z0-9_-]）")
    if not isinstance(seq, int) or not (1 <= seq <= 99):
        raise ValueError(f"seq 非法: {seq!r}（需 1-99 整数）")
    now = now or datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d%H%M%S")
    # 秒段必须为 14 位数字（DoD：\d{14} 校验）
    if not _TS_RE.match(ts):
        raise ValueError(f"id 秒段非法: {ts!r}（需 \\d{{14}}）")
    return f"{ws}-{ts}-{seq:02d}"