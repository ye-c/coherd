"""coherd.push 单元测试：role/ws/peer 派生、日志 append 格式、并发、送达失败仍记账。

零依赖（stdlib unittest），用临时 log_path 隔离，不触碰真实 ~/.config/coherd/events.log。
"""

import importlib
import json
import os
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from coherd import push as P
from coherd import tracker as T


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
            "w2p",
            "coordinator",
            "reviewer",
            "m1",
            ts="2026-08-27T00:00:00Z",
            body="原始正文",
        )
        line = P.event_line(ev)
        self.assertEqual(json.loads(line), ev)
        # 字段序追加 body 于末尾：ws,from,to,type,msg_id,ts,body
        self.assertEqual(
            list(ev.keys()),
            ["ws", "from", "to", "type", "msg_id", "ts", "body"],
        )
        # body = 未经标记前缀的原始正文
        self.assertEqual(ev["body"], "原始正文")
        # 缺省期待回执
        self.assertEqual(ev["type"], "feedback")

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
        self.assertEqual(json.loads(lines[0])["type"], "feedback")

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
        self.assertEqual(seen["msg"], "[coordinator|feedback]: [reviewer]: ok")
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
            self.assertEqual(ev["type"], "feedback")
            self.assertTrue(ev["msg_id"])
            ids.add(ev["msg_id"])
        self.assertEqual(len(ids), n)  # msg_id 全唯一


class LogPathTest(unittest.TestCase):
    """无 log_path 的日志路径决策：有合格 session 目录 → per-session；冷启动无 → 全局兜底。
    仿 test_tracker：COHERD_CONFIG_HOME 指临时目录 + reload(T)/reload(P) 隔离，
    使 push.DEFAULT_LOG 与 tracker.TASKS_DIR 均指向临时根，不触真实 ~/.config。"""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        os.environ["COHERD_CONFIG_HOME"] = self._tmp.name
        importlib.reload(T)
        importlib.reload(P)
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        os.environ.pop("COHERD_CONFIG_HOME", None)
        importlib.reload(T)
        importlib.reload(P)

    def _log_lines(self, path: Path) -> list[dict]:
        return [
            json.loads(l)
            for l in path.read_text(encoding="utf-8").splitlines()
            if l
        ]

    def test_no_log_path_writes_session_events_log(self):
        """有含 task.md 的 session 目录 → 写 session/events.log，body 记原始正文，不写全局。"""
        session = T.session_dir_for("w9p", create=True)
        (session / "w9p-20260828000000.task.md").write_text(
            "---\nid: w9p-20260828000000\nws: w9p\n---\n", encoding="utf-8"
        )
        r = P.run(
            "w9p-reviewer", "原始正文", ws="w9p", role="executor", sender=_delivered
        )
        self.assertEqual(r["log_path"], str(session / "events.log"))
        ev = self._log_lines(session / "events.log")
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["body"], "原始正文")  # 未带标记前缀
        self.assertNotIn("executor|feedback", ev[0]["body"])
        self.assertFalse(P.DEFAULT_LOG.exists())  # 有 session 目录时不写全局

    def test_no_log_path_cold_start_falls_back_global(self):
        """冷启动无合格 session 目录 → 回退全局 DEFAULT_LOG，且不自建空 session 目录。"""
        before = set(T.TASKS_DIR.glob("w9q-*/")) if T.TASKS_DIR.is_dir() else set()
        r = P.run("w9q-reviewer", "hi", ws="w9q", role="executor", sender=_delivered)
        self.assertEqual(r["log_path"], str(P.DEFAULT_LOG))
        ev = self._log_lines(P.DEFAULT_LOG)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["body"], "hi")
        # 防目录爆炸：未自建空 session 目录
        after = set(T.TASKS_DIR.glob("w9q-*/")) if T.TASKS_DIR.is_dir() else set()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
