import unittest
from coherd.push import parse_agent_name, Identity


class ParseAgentNameTest(unittest.TestCase):
    def test_single_instance(self):
        # AC1: 单实例名
        i = parse_agent_name("w2p-executor", "w2p")
        self.assertEqual(i, Identity("executor", 1, False))
        self.assertEqual(i.display, "executor")

    def test_multi_instance(self):
        # AC2: 多实例名
        i = parse_agent_name("w2p-executor-2", "w2p")
        self.assertEqual(i, Identity("executor", 2, True))
        self.assertEqual(i.display, "executor#2")

    def test_unknown_name(self):
        # AC3: 未知名（无自身前缀）
        i = parse_agent_name("test-worker", "w2p")
        self.assertEqual(i, Identity("test-worker", 1, False))
        self.assertEqual(i.display, "test-worker")

    def test_invalid_index(self):
        # AC4: 非法序号形态
        i1 = parse_agent_name("w2p-executor-0", "w2p")
        self.assertEqual(i1, Identity("executor-0", 1, False))
        
        i2 = parse_agent_name("w2p-executor-02", "w2p")
        self.assertEqual(i2, Identity("executor-02", 1, False))
        
        i3 = parse_agent_name("w2p-executor-2x", "w2p")
        self.assertEqual(i3, Identity("executor-2x", 1, False))

    def test_missing_ws_prefix(self):
        # AC5: 不含自身 workspace 前缀
        i1 = parse_agent_name("other-led", "w2p")
        self.assertEqual(i1, Identity("other-led", 1, False))
        
        i2 = parse_agent_name("libero", "w2p")
        self.assertEqual(i2, Identity("libero", 1, False))

    def test_explicit_index_one(self):
        # AC6: 显式序号 1
        i = parse_agent_name("w2p-executor-1", "w2p")
        self.assertEqual(i, Identity("executor", 1, True))
        self.assertEqual(i.display, "executor#1")

    def test_explicit_role_fallback(self):
        # AC11b: 外部显式指定角色为词汇外原串
        i = parse_agent_name("test-worker", "w2p")
        self.assertEqual(i, Identity("test-worker", 1, False))
        self.assertEqual(i.display, "test-worker")

    def test_ac14_guardian_role_vocabulary(self):
        from pathlib import Path
        from coherd.push import CONTRACT_ROLES
        roles_dir = Path(__file__).parents[1] / "roles"
        doc_roles = {
            p.stem for p in roles_dir.glob("*.md")
            if not p.stem.startswith("CONTRACT")
        }
        self.assertTrue(doc_roles.issubset(CONTRACT_ROLES))

if __name__ == "__main__":
    unittest.main()
