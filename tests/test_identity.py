import unittest
from coherd.push import parse_agent_name

class IdentityTest(unittest.TestCase):
    def test_ac1_single_instance(self):
        id_obj = parse_agent_name("ws-executor", "ws")
        self.assertEqual(id_obj.role, "executor")
        self.assertEqual(id_obj.index, 1)
        self.assertEqual(id_obj.display, "executor")

    def test_ac2_multi_instance(self):
        id_obj = parse_agent_name("ws-executor-2", "ws")
        self.assertEqual(id_obj.role, "executor")
        self.assertEqual(id_obj.index, 2)
        self.assertEqual(id_obj.display, "executor#2")

    def test_ac3_unknown_name_fails_open(self):
        id_obj = parse_agent_name("test-worker", "ws")
        self.assertEqual(id_obj.role, "test-worker")
        self.assertEqual(id_obj.index, 1)
        self.assertEqual(id_obj.display, "test-worker")

    def test_ac4_invalid_index_fails_open(self):
        for name in ["ws-executor-0", "ws-executor-02", "ws-executor-2x"]:
            id_obj = parse_agent_name(name, "ws")
            base = name.replace("ws-", "")
            self.assertEqual(id_obj.role, base)
            self.assertEqual(id_obj.index, 1)
            self.assertEqual(id_obj.display, base)

    def test_ac5_no_ws_prefix_behaves_same(self):
        id_obj1 = parse_agent_name("other-led", "ws")
        self.assertEqual(id_obj1.role, "other-led")
        self.assertEqual(id_obj1.index, 1)
        self.assertEqual(id_obj1.display, "other-led")

        id_obj2 = parse_agent_name("libero", "ws")
        self.assertEqual(id_obj2.role, "libero")
        self.assertEqual(id_obj2.index, 1)
        self.assertEqual(id_obj2.display, "libero")

    def test_ac6_explicit_index_display_differs_from_ac1(self):
        id_obj = parse_agent_name("ws-executor-1", "ws")
        self.assertEqual(id_obj.role, "executor")
        self.assertEqual(id_obj.index, 1)
        self.assertEqual(id_obj.display, "executor#1")

    def test_ac14_guardian_role_vocabulary(self):
        from pathlib import Path
        from coherd.push import CONTRACT_ROLES
        roles_dir = Path(__file__).parents[1] / "roles"
        doc_roles = {
            p.stem for p in roles_dir.glob("*.md")
            if not p.stem.startswith("CONTRACT")
        }
        self.assertTrue(doc_roles.issubset(CONTRACT_ROLES))

    def test_pure_function_no_env_no_io(self):
        import sys
        mod = sys.modules['coherd.push']
        # parse_agent_name should not touch environment
        import os
        old_env = dict(os.environ)
        os.environ["COHERD_ROLE"] = "should_not_matter"
        try:
            res = parse_agent_name("ws-executor-2", "ws")
            self.assertEqual(res.role, "executor")
            self.assertEqual(res.index, 2)
        finally:
            os.environ.clear()
            os.environ.update(old_env)

if __name__ == '__main__':
    unittest.main()