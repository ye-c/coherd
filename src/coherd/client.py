"""coherd.client — herdr socket 短连接请求-响应客户端（共享 helper）。

把 watch.enum_panes 的 socket connect + 流读完整 JSON 响应抽成模块级 helper，
push 的 role 自派生末级 fallback 同源复用，避免在两个消费者里复制 socket 代码。
"""

from __future__ import annotations

import json
import socket


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


def agent_list(socket_path: str) -> list:
    """独立短连接调 agent.list，返回 agents 列表；无 socket 或失败返回 []。

    请求-响应短连接（响应后服务端关闭），故不复用 watch 的长订阅连接。
    """
    if not socket_path:
        return []
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(socket_path)
        req = json.dumps(
            {"jsonrpc": "2.0", "id": "cli_list", "method": "agent.list", "params": {}}
        )
        s.sendall(req.encode("utf-8") + b"\n")
        line = _recv_full_json(s)
        return (line.get("result") or {}).get("agents") or []
    except Exception:
        return []
    finally:
        try:
            s.close()
        except OSError:
            pass
