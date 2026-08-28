"""coherd.push 单元测试：role/ws/peer 派生、日志 append 格式、并发、送达失败仍记账。

零依赖（stdlib unittest），用临时 log_path 隔离，不触碰真实 ~/.config/coherd/events.log。
"""

import json
import os
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from coherd import push as P


def _delivered(peer: str, msg: str) -> bool:
    return True


def _tmp_log() -> tuple[Path, object]:
    d = TemporaryDirectory()
    return Path(d.name) / "events.log", d.cleanup


class EnvMixin:
    """保存/恢复涉及的 env 变量。"""

    KEYS = (
        "HERDR_WORKSPACE_ID",
        "COHERD_ROLE",
        "HERDR_AGENT_NAME",
        "HERDR_PANE_ID",
        "HERDR_SOCKET_PATH",
    )

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in self.KEYS}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class DerivationTest(EnvMixin, unittest.TestCase):
    def test_role_ws_peer_explicit(self):
        path, cleanup = _tmp_log()
        self.addCleanup(cleanup)
        r = P.run(
            "w2p-reviewer",
            "[reviewer]: hi",
            ws="w2p",
            role="coordinator",
            log_path=path,
            sender=_delivered,
        )
        self.assertEqual(r["ws"], "w2p")
        self.assertEqual(r["from"], "coordinator")
        self.assertEqual(r["to"], "reviewer")  # peer agent 去 ws- 前缀

    def test_ws_from_env_lower(self):
        path, cleanup = _tmp_log()
        self.addCleanup(cleanup)
        os.environ["HERDR_WORKSPACE_ID"] = "w2P"  # 大写 → 小写短号
        os.environ.pop("COHERD_ROLE", None)
        os.environ["HERDR_AGENT_NAME"] = "w2p-executor"
        r = P.run(
            "w2p-reviewer", "m", ws=None, role=None, log_path=path, sender=_delivered
        )
        self.assertEqual(r["ws"], "w2p")
        self.assertEqual(r["from"], "executor")  # 自身 agent 名派生

    def test_role_from_copherd_role_env(self):
        path, cleanup = _tmp_log()
        self.addCleanup(cleanup)
        os.environ.pop("HERDR_AGENT_NAME", None)
        os.environ["COHERD_ROLE"] = "libero"
        r = P.run(
            "w2a-coordinator",
            "m",
            ws="w2a",
            role=None,
            log_path=path,
            sender=_delivered,
        )
        self.assertEqual(r["from"], "libero")
        self.assertEqual(r["to"], "coordinator")

    def test_missing_ws_raises(self):
        path, cleanup = _tmp_log()
        self.addCleanup(cleanup)
        for k in self.KEYS:
            os.environ.pop(k, None)
        with self.assertRaises(ValueError):
            P.run("w2p-reviewer", "m", ws=None, role="executor", log_path=path)

    def test_missing_role_raises(self):
        path, cleanup = _tmp_log()
        self.addCleanup(cleanup)
        os.environ["HERDR_WORKSPACE_ID"] = "w2p"
        os.environ.pop("COHERD_ROLE", None)
        os.environ.pop("HERDR_AGENT_NAME", None)
        # 末级 fallback 也无 socket env → 自派生无果 → raise（不撞真实 socket）
        os.environ.pop("HERDR_PANE_ID", None)
        os.environ.pop("HERDR_SOCKET_PATH", None)
        with self.assertRaises(ValueError):
            P.run("w2p-reviewer", "m", ws="w2p", role=None, log_path=path)

    def test_self_role_fn_stub_derives_role(self):
        """注入 self_role_fn（同 sender 模式）代替 agent.list fallback，零 env。"""
        path, cleanup = _tmp_log()
        self.addCleanup(cleanup)
        for k in self.KEYS:
            os.environ.pop(k, None)
        r = P.run(
            "w2t-reviewer",
            "m",
            ws="w2t",
            role=None,
            log_path=path,
            sender=_delivered,
            self_role_fn=lambda: "w2t-executor",
        )
        self.assertEqual(r["ws"], "w2t")
        self.assertEqual(r["from"], "executor")  # fallback 返回 name → derive_role
        self.assertEqual(r["to"], "reviewer")

    def test_agent_list_fallback_hits(self):
        """零 env 时 agent.list 按 pane_id 命中自身 name → 派生成功（不碰真实 socket）。"""
        path, cleanup = _tmp_log()
        self.addCleanup(cleanup)
        for k in self.KEYS:
            os.environ.pop(k, None)
        os.environ["HERDR_PANE_ID"] = "w2T:p9"
        os.environ["HERDR_SOCKET_PATH"] = "/tmp/fake.sock"
        with mock.patch.object(
            P,
            "agent_list",
            return_value=[
                {"name": "w2t-executor", "pane_id": "w2T:p9", "workspace_id": "w2t"},
            ],
        ):
            r = P.run(
                "w2t-reviewer",
                "m",
                ws="w2t",
                role=None,
                log_path=path,
                sender=_delivered,
            )
        self.assertEqual(r["from"], "executor")


class AppendFormatTest(unittest.TestCase):
    def test_event_line_fields(self):
        ev = P.make_event(
            "send", "w2p", "coordinator", "reviewer", "m1", ts="2026-08-27T00:00:00Z"
        )
        line = P.event_line(ev)
        self.assertEqual(json.loads(line), ev)
        # 字段序与 spec §4/§6 一致
        self.assertEqual(
            list(ev.keys()), ["op", "ws", "from", "to", "msg_id", "ts", "expect_reply"]
        )
        # 缺省期待回执
        self.assertTrue(ev["expect_reply"])

    def test_append_writes_single_json_line(self):
        path, cleanup = _tmp_log()
        self.addCleanup(cleanup)
        P.append_event(path, '{"op":"send"}')
        P.append_event(path, '{"op":"send","n":2}')
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l]
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["op"], "send")
        self.assertEqual(json.loads(lines[1])["n"], 2)


class DeliveryTest(unittest.TestCase):
    def test_delivery_failure_still_logs(self):
        path, cleanup = _tmp_log()
        self.addCleanup(cleanup)
        r = P.run(
            "w2p-reviewer",
            "m",
            ws="w2p",
            role="executor",
            log_path=path,
            sender=lambda p, m: False,
        )
        self.assertFalse(r["delivered"])
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l]
        self.assertEqual(len(lines), 1)  # 送达失败日志行不丢
        self.assertEqual(json.loads(lines[0])["op"], "send")

    def test_delivery_success_passes_peer_msg(self):
        path, cleanup = _tmp_log()
        self.addCleanup(cleanup)
        seen = {}

        def sender(peer, msg):
            seen["peer"], seen["msg"] = peer, msg
            return True

        r = P.run(
            "w2p-reviewer",
            "[reviewer]: ok",
            ws="w2p",
            role="coordinator",
            log_path=path,
            sender=sender,
        )
        self.assertTrue(r["delivered"])
        self.assertEqual(seen["peer"], "w2p-reviewer")
        self.assertEqual(seen["msg"], "[reviewer]: ok")
        self.assertEqual(r["log_path"], str(path))


class ConcurrencyTest(unittest.TestCase):
    def test_concurrent_appends_no_overwrite_no_corruption(self):
        path, cleanup = _tmp_log()
        self.addCleanup(cleanup)
        n = 60
        errs = []

        def worker(i):
            try:
                P.run(
                    f"w2p-peer{i % 3}",
                    "m",
                    ws="w2p",
                    role="executor",
                    log_path=path,
                    sender=_delivered,
                )
            except Exception as e:  # noqa: BLE001
                errs.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errs, [])
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l]
        self.assertEqual(len(lines), n)  # 无丢失无覆盖
        ids = set()
        for l in lines:
            ev = json.loads(l)
            self.assertEqual(ev["op"], "send")
            self.assertTrue(ev["msg_id"])
            ids.add(ev["msg_id"])
        self.assertEqual(len(ids), n)  # msg_id 全唯一


if __name__ == "__main__":
    unittest.main()
