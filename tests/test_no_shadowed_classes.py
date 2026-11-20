"""守护: 同一测试文件内顶层类名必须唯一。

同名类后者静默覆盖前者，前者的用例永远不会被收集——`tests/test_push.py` 曾
因此藏了 3 个死用例（`MultiInstanceTest` 两份定义）。措辞级守护挡不住这种
结构性问题，只能靠 AST 查。
"""

import ast
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent


def duplicate_class_names(source: str) -> list[str]:
    """返回同一份源码里出现多次的顶层类名（排序去重）。"""
    tree = ast.parse(source)
    names = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
    return sorted({name for name in names if names.count(name) > 1})


class NoShadowedClassesTest(unittest.TestCase):
    def test_detector_flags_duplicate_classes(self):
        # 自测: 检出器本身不能失灵
        src = "class A:\n    pass\n\n\nclass B:\n    pass\n\n\nclass A:\n    pass\n"
        self.assertEqual(["A"], duplicate_class_names(src))

    def test_no_duplicate_classes_in_tests(self):
        found = {}
        for path in sorted(TESTS_DIR.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            dups = duplicate_class_names(path.read_text(encoding="utf-8"))
            if dups:
                found[str(path.relative_to(TESTS_DIR))] = dups
        self.assertEqual(
            {},
            found,
            "同一文件出现重名顶层类（后者覆盖前者，前者用例永不收集）: %s" % found,
        )


if __name__ == "__main__":
    unittest.main()