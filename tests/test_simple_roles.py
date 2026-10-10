"""T1 单元: simple 模式角色名派生 —— lead/dev 沿用 `${ws}-` 前缀剥离, 无新映射表 (spec D3/T1)。

零依赖 stdlib unittest, 与 tests/ 其余用例同风格:
    python -m unittest discover -s tests
"""

import unittest

from coherd.push import derive_role


class SimpleRoleDerivationTest(unittest.TestCase):
    """T1: derive_role(lead/dev 名, ws) 正确派生, CLI 侧零改动假设成立。"""

    def test_lead_dev_prefix_strip(self):
        self.assertEqual(derive_role("w5f-lead", "w5f"), "lead")
        self.assertEqual(derive_role("w5f-dev", "w5f"), "dev")

    def test_three_role_names_unaffected(self):
        # 双角色模式不改变三角色派生
        self.assertEqual(derive_role("w5f-coordinator", "w5f"), "coordinator")
        self.assertEqual(derive_role("w5f-executor", "w5f"), "executor")
        self.assertEqual(derive_role("w5f-reviewer", "w5f"), "reviewer")

    def test_foreign_ws_prefix_not_stripped(self):
        # 跨 label/跨集群无串: 只有自身 ws 前缀被剥离
        self.assertEqual(derive_role("w2p-lead", "w5f"), "w2p-lead")
        self.assertEqual(derive_role("w2p-dev", "w5f"), "w2p-dev")

    def test_no_prefix_passthrough(self):
        # libero / standalone 兜底: 无前缀原样返回
        self.assertEqual(derive_role("libero", "w5f"), "libero")


if __name__ == "__main__":
    unittest.main()