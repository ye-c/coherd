"""守护: 轮询禁令的可执行收敛 —— read 唯一许可 + 配额 / 待机定义 / 进度查询唯一化。

对应 spec `way-20261120040157-01` AC1-AC5（措辞型约束机检化, 见 spec FR6 / D6）。
只查文档措辞与授权计数, 不解析语义:

    PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_contract*.py'
"""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROLES = REPO / "roles"
ACTIVITY_DOC = REPO / "docs" / "activity.md"

# 角色契约文档全集（roles/templates/ 是骨架产物, 不在授权面内）
ROLE_DOCS = (
    "CONTRACT.md",
    "CONTRACT-simple.md",
    "coordinator.md",
    "executor.md",
    "reviewer.md",
    "dev.md",
    "led.md",
    "libero.md",
)
# 三份角色执行文档（AC3 覆盖面）
PER_ROLE_DOCS = ("coordinator.md", "executor.md", "reviewer.md")

READ = "herdr agent read"
# 肯定式授权措辞（否定式「不用于 / 不作」不算授权）
PERMISSIVE = re.compile(r"(仅用于|只用于|可用于|用于核对状态|用于查证据)")
# 否定式表述（保留既有的禁令句, 不构成新授权）
NEGATIVE = re.compile(r"(不要用|不用于|不作|不得用|只按)")


def _read(name: str) -> str:
    return (ROLES / name).read_text(encoding="utf-8")


def _lines(name: str):
    return enumerate(_read(name).splitlines(), 1)


class ReadAuthorizationTest(unittest.TestCase):
    """AC1: read 许可性表述恰 1 处, 且该处同条含配额与用途限定。"""

    def _permissive_lines(self):
        hits = []
        for name in ROLE_DOCS:
            for lineno, line in _lines(name):
                if READ in line and PERMISSIVE.search(line):
                    hits.append((name, lineno, line))
        return hits

    def test_ac1_exactly_one_permissive_statement(self):
        hits = self._permissive_lines()
        self.assertEqual(
            1,
            len(hits),
            "read 许可性表述应恰 1 处, 实得 %d 处: %s"
            % (len(hits), [(n, l) for n, l, _ in hits]),
        )

    def test_ac1_permission_carries_quota_and_purpose(self):
        hits = self._permissive_lines()
        self.assertTrue(hits, "未找到唯一许可处")
        line = hits[0][2]
        self.assertIn("≤1 次", line, "唯一许可处缺可数配额")
        self.assertIn("重发前证据", line, "唯一许可处缺用途限定")

    def test_other_mentions_are_references_not_grants(self):
        # 除唯一许可处外, 其余 read 提及必须是否定引用或指向 CONTRACT §0 pull 条（不复制授权文字）
        for name in ROLE_DOCS:
            for lineno, line in _lines(name):
                if READ not in line:
                    continue
                if PERMISSIVE.search(line):
                    continue  # 唯一许可处本身, 由上面两条管
                self.assertTrue(
                    NEGATIVE.search(line) or "pull" in line,
                    "%s:%d read 提及既非唯一许可处也非否定引用/§0 pull 条指针: %s"
                    % (name, lineno, line.strip()),
                )


class ActivityAuthorizationTest(unittest.TestCase):
    """AC2: 角色文档无 agent 侧活性判定授权; 排查文档自述用户专用。"""

    AUTHORIZING = re.compile(r"events\.log.{0,40}(介入|判断活性|判活性|判活)")
    AUTHORIZING_PEER = re.compile(r"(可据|可依).{0,20}peer 状态.{0,20}(介入|判断)")

    def test_ac2_no_agent_liveness_authorization(self):
        for name in ROLE_DOCS:
            for lineno, line in _lines(name):
                self.assertIsNone(
                    self.AUTHORIZING.search(line),
                    "%s:%d 仍授权 agent 据 events.log 判活性: %s"
                    % (name, lineno, line.strip()),
                )
                self.assertIsNone(
                    self.AUTHORIZING_PEER.search(line),
                    "%s:%d 仍授权 agent 据 peer 状态介入: %s"
                    % (name, lineno, line.strip()),
                )

    def test_ac2_activity_doc_declares_human_only(self):
        text = ACTIVITY_DOC.read_text(encoding="utf-8")
        self.assertIn("用户专用", text)
        self.assertIn("agent 侧无等价授权", text)


class StandbyTest(unittest.TestCase):
    """AC3: 三份角色执行文档均给「待机 = 本回合结束」的可执行定义。"""

    def test_ac3_standby_defined_as_turn_end(self):
        for name in PER_ROLE_DOCS:
            self.assertIn(
                "本回合结束",
                _read(name),
                "%s 缺「待机 = 本回合结束」可执行定义" % name,
            )


class ProgressQueryTest(unittest.TestCase):
    """AC4: 进度查询唯一 = coherd task list, 且明示另两者不是进度手段。"""

    def setUp(self):
        self.text = _read("coordinator.md")

    def test_ac4_unique_progress_means(self):
        self.assertIn("coherd task list", self.text)
        self.assertIn("进度查询（唯一手段）", self.text)

    def test_ac4_excludes_peer_read_and_events_log(self):
        self.assertGreaterEqual(
            self.text.count("不是进度查询手段"),
            2,
            "须同时明示「读对端全文」与「读 events.log」都不是进度查询手段",
        )


class ProhibitedPollingHitsTest(unittest.TestCase):
    """DoD3: 探活禁令以「目的禁止 + 例示」落 CONTRACT §7, 且 coordinator 写死分派后收回合。"""

    def _contract_s7(self) -> str:
        text = _read("CONTRACT.md")
        start = text.index("## 7. 事件驱动交接")
        end = text.index("## 9.", start)
        return text[start:end]

    def test_contract_s7_bans_by_purpose_not_by_command(self):
        seg = self._contract_s7()
        self.assertIn("判据是目的", seg, "§7 缺目的禁止判据, 命令名枚举会被换名绕过")
        self.assertIn("非穷举", seg, "§7 例示须声明非穷举, 否则等于回到命令枚举")

    def test_contract_s7_names_both_observed_bypasses(self):
        seg = self._contract_s7()
        self.assertIn("herdr agent list", seg, "§7 未点名 agent list 这条实际绕过路径")
        self.assertIn("events.log", seg, "§7 未点名 events.log 这条实际绕过路径")

    def test_coordinator_ends_turn_after_dispatch(self):
        text = _read("coordinator.md")
        self.assertIn("分派发出即结束本回合", text, "coordinator 缺分派后正向收回合动作")
        self.assertIn("不得再发任何 tool call", text, "分派后收回合未写成可判动作")
        self.assertIn("全部发出后", text, "分派后收回合缺『本轮次全部分派』限定, 多 executor 无法完成分派")


class SimpleModeReferenceTest(unittest.TestCase):
    """AC5: simple 侧指向 CONTRACT §0 同一唯一许可处, 不复制授权文字。"""

    def test_ac5_simple_read_points_to_contract(self):
        for name in ("CONTRACT-simple.md", "dev.md"):
            for _, line in _lines(name):
                if READ not in line:
                    continue
                self.assertIsNone(
                    PERMISSIVE.search(line),
                    "%s: simple 侧复制了 read 授权文字: %s" % (name, line.strip()),
                )
                self.assertIn("CONTRACT", line, "%s: read 提及未指向 CONTRACT" % name)
                self.assertTrue(
                    "pull" in line or NEGATIVE.search(line),
                    "%s: read 提及未指向 §0 pull 条也未带否定表述: %s"
                    % (name, line.strip()),
                )


if __name__ == "__main__":
    unittest.main()