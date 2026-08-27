"""coherd.watch 单元测试：账本重放/反向清账/offset 续读、decide 幂等/节流/escalate、
事件解析、pid 锁、端到端 _handle_event。零依赖（stdlib unittest），用临时目录隔离，
socket 用假对象注入，不连真实 herdr。"""
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from coherd import watch as W




def _tmp(base) -> Path:
    """创建临时目录并注册为当前测试 case 的 cleanup。base 为 TestCase 实例。"""
    d = TemporaryDirectory()
    base.addCleanup(d.cleanup)
    return Path(d.name)


class ReplayTest(unittest.TestCase):
    def setUp(self):
        self.dir = _tmp(self)

    def _log(self, lines):
        p = self.dir / "push-events.log"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def test_replay_builds_pending(self):
        log = self._log([
            json.dumps({"op": "send", "ws": "w2p", "from": "coordinator", "to": "reviewer", "msg_id": "1", "ts": "t"}),
            json.dumps({"op": "send", "ws": "w2p", "from": "executor", "to": "reviewer", "msg_id": "2", "ts": "t"}),
        ])
        l = W.Ledger()
        off = l.replay(log, 0)
        self.assertEqual(l.owner("w2p", "reviewer"), "executor")  # 最后一条覆盖
        self.assertEqual(off, log.stat().st_size)

    def test_reverse_clears_pending(self):
        # reviewer 欠 executor；reviewer 反向发给 executor → 清
        log = self._log([
            json.dumps({"op": "send", "ws": "w2p", "from": "executor", "to": "reviewer", "msg_id": "1", "ts": "t"}),
            json.dumps({"op": "send", "ws": "w2p", "from": "reviewer", "to": "executor", "msg_id": "2", "ts": "t"}),
        ])
        l = W.Ledger()
        l.replay(log, 0)
        self.assertIsNone(l.owner("w2p", "reviewer"))  # reviewer 已回执
        self.assertEqual(l.owner("w2p", "executor"), "reviewer")  # 新欠：executor 欠 reviewer

    def test_offset_contiue_no_replay_duplicate(self):
        log = self._log([
            json.dumps({"op": "send", "ws": "w2p", "from": "coordinator", "to": "reviewer", "msg_id": "1", "ts": "t"}),
        ])
        l = W.Ledger()
        off = l.replay(log, 0)
        # 追加新行，从上次 offset 续读
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"op": "send", "ws": "w2p", "from": "executor", "to": "reviewer", "msg_id": "2", "ts": "t"}) + "\n")
        off2 = l.replay(log, off)
        # reviewer 仍欠 executor（未回执），offset 前进
        self.assertEqual(l.owner("w2p", "reviewer"), "executor")
        self.assertGreater(off2, off)

    def test_rollback_zero_on_truncated(self):
        log = self._log([
            json.dumps({"op": "send", "ws": "w2p", "from": "coordinator", "to": "reviewer", "msg_id": "1", "ts": "t"}),
        ])
        l = W.Ledger()
        l.replay(log, 0)
        # 模拟轮转：文件被截断变短，offset 大于 size → 从零重放
        log.write_text(json.dumps({"op": "send", "ws": "w2p", "from": "executor", "to": "reviewer", "msg_id": "3", "ts": "t"}) + "\n", encoding="utf-8")
        off = l.replay(log, 999999)
        self.assertEqual(l.owner("w2p", "reviewer"), "executor")
        self.assertEqual(off, log.stat().st_size)

    def test_bad_lines_skipped(self):
        log = self.dir / "push-events.log"
        log.write_text('{"op":"send","ws":"w2p","from":"coordinator","to":"reviewer","msg_id":"1","ts":"t"}\nnot json\n', encoding="utf-8")
        l = W.Ledger()
        l.replay(log, 0)
        self.assertEqual(l.owner("w2p", "reviewer"), "coordinator")


class DecideTest(unittest.TestCase):
    def test_no_owner_skip(self):
        self.assertEqual(W.decide(None, 0, 0.0, 100.0), (W.SKIP, 0, 0.0))

    def test_first_remind_then_escalate_then_stop(self):
        # owner 存在 → 第1次 REMIND
        a, c, last = W.decide("coordinator", 0, 0.0, 10.0, throttle=5.0)
        self.assertEqual((a, c), (W.REMIND, 1))
        self.assertEqual(last, 10.0)
        # 节流内（now=12 < 15）→ SKIP 幂等
        a2, c2, last2 = W.decide("coordinator", c, last, 12.0, throttle=5.0)
        self.assertEqual((a2, c2), (W.SKIP, 1))
        # 节流过了（now=16 >= 15）且 count==1 → ESCALATE
        a3, c3, last3 = W.decide("coordinator", c, last, 16.0, throttle=5.0)
        self.assertEqual((a3, c3), (W.ESCALATE, 2))
        # count>=2 → 停止循环 SKIP
        a4, c4, _ = W.decide("coordinator", c3, last3, 30.0, throttle=5.0)
        self.assertEqual((a4, c4), (W.SKIP, 2))


class RoleFromEventTest(unittest.TestCase):
    """真实 herdr 事件载荷下 role_from_event 的行为（reviewer P1 验证要求）。

    真实现：agent=CLI 标签（claude/pi/omp）、display_agent=None、title=None，
    role 名不在载荷内 → role_from_event 应返回 None，证明主路径须走 agent.list。
    """

    def test_real_payload_returns_none(self):
        # 真实 pane.agent_status_changed 载荷形态（黑盒 pane.list/agent.list 实测）
        data = {"pane_id": "w2P:p2", "workspace_id": "w2P",
                "agent_status": "idle", "agent": "claude",
                "display_agent": None, "title": None}
        self.assertIsNone(W.role_from_event(data, "w2p"))

    def test_none_when_missing(self):
        self.assertIsNone(W.role_from_event({"agent": None}, "w2p"))
        self.assertIsNone(W.role_from_event({}, "w2p"))

    def test_legacy_payload_returns_role(self):
        # 兜底路径仍可用（若某 CLI 上报了带 role 的 title/agent）
        data = {"title": "✳ Initialize w2p-executor standby"}
        self.assertEqual(W.role_from_event(data, "w2p"), "executor")


class BuildPaneMapTest(unittest.TestCase):
    """P1 主路径：agent.list → derive_role 建 pane→role 映射（reviewer 验证要求）。"""

    def test_builds_pane_role_and_agent_map(self):
        w = W.Watch(ws="w2p")
        agents = [
            {"name": "w2p-coordinator", "pane_id": "w2P:p1", "agent": "pi"},
            {"name": "w2p-reviewer", "pane_id": "w2P:p2", "agent": "claude"},
            {"name": "w2p-executor", "pane_id": "w2P:p3", "agent": "omp"},
        ]
        panes = w.build_pane_map(agents, "w2p")
        self.assertEqual(sorted(panes), ["w2P:p1", "w2P:p2", "w2P:p3"])
        self.assertEqual(w.panes["w2P:p1"], "coordinator")
        self.assertEqual(w.panes["w2P:p2"], "reviewer")
        self.assertEqual(w.panes["w2P:p3"], "executor")
        self.assertEqual(w.agents["w2P:p2"], "w2p-reviewer")  # 全名供 _remind peer

    def test_skips_entries_without_name_or_pane(self):
        w = W.Watch(ws="w2p")
        agents = [{"name": "w2p-reviewer", "pane_id": "w2P:p2", "agent": "claude"},
                  {"name": None, "pane_id": "w2P:x", "agent": "pi"},
                  {"name": "w2p-libero", "pane_id": None, "agent": "omp"}]
        panes = w.build_pane_map(agents, "w2p")
        self.assertEqual(panes, ["w2P:p2"])
        self.assertNotIn("w2P:x", w.panes)


class PidLockTest(unittest.TestCase):
    def setUp(self):
        self.dir = _tmp(self)
        self.w = W.Watch(pid_path=self.dir / "watch.pid")

    def test_acquire_then_reject_second(self):
        self.assertTrue(self.w.acquire_pid_lock())
        # 模拟第二个实例（同 pid 存活）→ 拒绝
        w2 = W.Watch(pid_path=self.w.pid_path)
        self.assertFalse(w2.acquire_pid_lock())
        self.w.release_pid_lock()

    def test_stale_lock_overwrites(self):
        # 旧 pid 不存在（99 万级 pid 通常未分配）→ 覆盖
        self.w.pid_path.write_text("99999999", encoding="utf-8")
        self.assertTrue(self.w.acquire_pid_lock())
        self.w.release_pid_lock()


class HandleEventTest(unittest.TestCase):
    """端到端 _handle_event：重放→idle→提醒→反向清账→停止。socket 用纯逻辑注入。"""

    def setUp(self):
        self.dir = _tmp(self)
        self.log = self.dir / "push-events.log"
        self.state = self.dir / "state.json"
        self.pid = self.dir / "watch.pid"
        self.sent = []

        def sender(peer, msg):
            self.sent.append((peer, msg))
            return True

        self.w = W.Watch(log_path=self.log, state_path=self.state, pid_path=self.pid,
                         ws="w2p", sender=sender, throttle=0.0)
        # P1：订阅前经 agent.list（真实形态）建 pane→role 映射；事件载荷的
        # agent 字段是 CLI 标签，不含 role 名。
        self.w.build_pane_map([
            {"name": "w2p-coordinator", "pane_id": "w2P:p1", "workspace_id": "w2P", "agent": "pi"},
            {"name": "w2p-reviewer", "pane_id": "w2P:p2", "workspace_id": "w2P", "agent": "claude"},
            {"name": "w2p-executor", "pane_id": "w2P:p3", "workspace_id": "w2P", "agent": "omp"},
            {"name": "w2p-libero", "pane_id": "w2P:p4", "workspace_id": "w2P", "agent": "omp"},
        ], "w2p")

    def _idle_event(self, pane="w2P:p2", ws_="w2P"):
        return {"event": "pane.agent_status_changed",
                "data": {"pane_id": pane, "workspace_id": ws_,
                         "agent_status": "idle", "agent": "claude"}}

    def test_idle_with_pending_reminds_then_clears_on_reverse(self):
        self.log.write_text(
            json.dumps({"op": "send", "ws": "w2p", "from": "coordinator", "to": "reviewer", "msg_id": "1", "ts": "t"}) + "\n",
            encoding="utf-8")
        # 第1次 idle → 提醒
        self.w._handle_event(self._idle_event())
        self.assertEqual(len(self.sent), 1)
        peer, msg = self.sent[0]
        self.assertEqual(peer, "w2p-reviewer")
        self.assertIn("coordinator", msg)
        self.assertIn("coherd push", msg)
        # 反向清账（reviewer 主动回复 coordinator，追加而非覆盖）→ pending 清
        with open(self.log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"op": "send", "ws": "w2p", "from": "reviewer", "to": "coordinator", "msg_id": "2", "ts": "t"}) + "\n")
        self.w._handle_event(self._idle_event())
        self.assertEqual(self.w.ledger.owner("w2p", "reviewer"), None)
        self.assertEqual(len(self.sent), 1)  # 无新增提醒

    def test_escalate_reaches_coordinator(self):
        self.log.write_text(
            json.dumps({"op": "send", "ws": "w2p", "from": "executor", "to": "reviewer", "msg_id": "1", "ts": "t"}) + "\n",
            encoding="utf-8")
        # throttle=0 → 第1次 REMIND，第2次 ESCALATE（escalate 到 coordinator）
        self.w._handle_event(self._idle_event())
        self.w._handle_event(self._idle_event())
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.sent[0][0], "w2p-reviewer")
        self.assertEqual(self.sent[1][0], "w2p-coordinator")
        # 第3次 → 停止（count>=2，幂等不再动）
        self.w._handle_event(self._idle_event())
        self.assertEqual(len(self.sent), 2)

    def test_ignores_non_idle_and_other_ws(self):
        self.log.write_text(
            json.dumps({"op": "send", "ws": "w2p", "from": "coordinator", "to": "reviewer", "msg_id": "1", "ts": "t"}) + "\n",
            encoding="utf-8")
        # 非 idle 事件 → 忽略
        ev = self._idle_event()
        ev["data"]["agent_status"] = "working"
        self.w._handle_event(ev)
        self.assertEqual(self.sent, [])
        # 其他 ws 事件 → 忽略（workspace_id=w2Z，watch 关注 w2p）
        self.w._handle_event(self._idle_event(pane="w2Z:p1", ws_="w2Z"))
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()