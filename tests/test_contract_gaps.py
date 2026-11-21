"""守护: 契约最小优化集（环境失败执行方、DoD变更失效、dev措辞、模板字面、超限判据统一）。

对应 tracker `wb8-20261121080423-01` 与 `wb8-20261121083424-01`（各条约束一条断言，锚点用短语不复制整句：
合法微调措辞不应转红，删条款/改语义必须转红）。只查文档措辞，不解析语义：

    PYTHONPATH=src .venv/bin/python3 -m unittest tests.test_contract_gaps -q
"""

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROLES = REPO / "roles"


def _read(name: str) -> str:
    return (ROLES / name).read_text(encoding="utf-8")


class EnvironmentFailureDispatchTest(unittest.TestCase):
    """AC1: CONTRACT-simple.md 环境失败由 led 下发前置修复分派，不自修环境。"""

    def test_env_failure_routes_to_repair_dispatch(self):
        doc = _read("CONTRACT-simple.md")
        self.assertIn("前置修复分派", doc)
        self.assertNotIn("修环境/补齐依赖后重跑", doc)


class InvalidationTriggerIncludesDoDTest(unittest.TestCase):
    """AC2: 失效触发条件包含规格或 DoD，遍历 5 份契约/角色文档。"""

    def test_invalidation_trigger_covers_spec_and_dod(self):
        target_files = [
            "CONTRACT.md",
            "CONTRACT-simple.md",
            "coordinator.md",
            "led.md",
            "reviewer.md",
        ]
        for name in target_files:
            with self.subTest(file=name):
                doc = _read(name)
                self.assertIn("规格或 DoD", doc)
                self.assertNotIn("spec 一旦变更", doc)
                self.assertNotIn("spec 变更后", doc)


class DevChangeDispatchNoWaitTest(unittest.TestCase):
    """AC3: dev 收到需求变更指示不等待、不轮询，视为 tracker 已更新。"""

    def test_dev_does_not_wait_for_tracker_update(self):
        doc = _read("dev.md")
        self.assertNotIn("等 tracker 更新", doc)
        self.assertIn("不等待、不轮询", doc)


class InvalidationTemplateLiteralTest(unittest.TestCase):
    """AC4: 重新分派失效声明模板字面为 因规格/DoD，遍历 4 份含模板文档。"""

    def test_invalidation_template_uses_spec_or_dod(self):
        target_files = [
            "CONTRACT.md",
            "CONTRACT-simple.md",
            "coordinator.md",
            "led.md",
        ]
        for name in target_files:
            with self.subTest(file=name):
                doc = _read(name)
                self.assertIn("因规格/DoD", doc)
                self.assertNotIn("因规格 <标识>", doc)


class ReviseLimitCriterionMechanicalTest(unittest.TestCase):
    """AC5: 超限判据机械可判（仍未 `approve`），遍历 3 份预审/超限相关文档。"""

    def test_revise_limit_criterion_is_mechanical(self):
        target_files = [
            "CONTRACT.md",
            "coordinator.md",
            "reviewer.md",
        ]
        for name in target_files:
            with self.subTest(file=name):
                doc = _read(name)
                self.assertNotIn("仍不收敛", doc)
                self.assertNotIn("仍有分歧", doc)
                self.assertIn("仍未 `approve`", doc)


class ExternalDiscussionSilentAbsorptionTest(unittest.TestCase):
    """AC6: 外部讨论方与旁路输入默认静默吸收（零打扰原则），严禁无动作诉求通知 peer。"""

    def test_contract_silent_absorption(self):
        doc = _read("CONTRACT.md")
        self.assertIn("静默吸收（零打扰原则）", doc)
        self.assertIn("严禁通知 executor 与 reviewer", doc)
        self.assertNotIn("对端感知", doc)

    def test_coordinator_silent_absorption(self):
        doc = _read("coordinator.md")
        self.assertIn("静默吸收（零打扰）", doc)
        self.assertIn("不得向 executor 或 reviewer 转发旁路知会通知", doc)
        self.assertNotIn("告知对端", doc)

    def test_contract_simple_silent_absorption(self):
        doc = _read("CONTRACT-simple.md")
        self.assertIn("静默吸收（零打扰原则）", doc)
        self.assertIn("严禁通知 dev", doc)
        self.assertNotIn("对端感知", doc)


class DeliveryNoPeerBroadcastTest(unittest.TestCase):
    """AC7: 整合交付与合并闭环单向只对用户，严禁向 peer 广播完工通知。"""

    def test_coordinator_delivery_no_peer_broadcast(self):
        doc = _read("coordinator.md")
        self.assertIn("交付即待机，严禁广播 peer", doc)
        self.assertIn("严禁向 executor / reviewer / libero 发送任何", doc)

    def test_contract_delivery_no_peer_broadcast(self):
        doc = _read("CONTRACT.md")
        self.assertIn("单向只对用户，严禁广播 peer", doc)
        self.assertIn("严禁向 executor / reviewer / libero 补发完工知会", doc)

    def test_simple_delivery_no_peer_broadcast(self):
        doc_led = _read("led.md")
        doc_simple = _read("CONTRACT-simple.md")
        self.assertIn("严禁向 dev 补发完工知会", doc_led)
        self.assertIn("严禁向 dev 补发完工知会", doc_simple)


if __name__ == "__main__":
    unittest.main()
