"""守护: 同一测试文件内顶层类名必须唯一。

同名类后者静默覆盖前者，前者的用例永远不会被收集——`tests/test_push.py` 曾
因此藏了 3 个死用例（`MultiInstanceTest` 两份定义）。措辞级守护挡不住这种
结构性问题，只能靠 AST 查。

**自遮蔽**：若本文件自己被追加一个同名类，unittest 收集到的用例会变少而不是
变红（谁都发现不了）。故扫描抽成 `scan()`，可直接脱离 unittest 执行：

    python3 tests/test_no_shadowed_classes.py     # 0 = 无重名; 1 = 有重名(打印文件+类名)

smoke 用这个直扫入口把「守护文件自身被遮蔽」也拦下。
"""

import ast
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent


def duplicate_class_names(source: str) -> list[str]:
    """返回同一份源码里出现多次的顶层类名（排序去重）。"""
    tree = ast.parse(source)
    names = [node.name for node in tree.body if isinstance(node, ast.ClassDef)]
    return sorted({name for name in names if names.count(name) > 1})


def scan(root: Path) -> dict[str, list[str]]:
    """扫整棵测试树，返回 {相对路径: [重名类...]}；空 dict = 干净。"""
    findings: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        dups = duplicate_class_names(path.read_text(encoding="utf-8"))
        if dups:
            findings[str(path.relative_to(root))] = dups
    return findings


def main(root: Path = TESTS_DIR) -> int:
    findings = scan(root)
    if not findings:
        return 0
    for file, names in findings.items():
        print("duplicate top-level class: %s -> %s" % (file, ", ".join(names)))
    return 1


class NoShadowedClassesTest(unittest.TestCase):
    def test_detector_flags_duplicate_classes(self):
        # 自测: 检出器本身不能失灵
        src = "class A:\n    pass\n\n\nclass B:\n    pass\n\n\nclass A:\n    pass\n"
        self.assertEqual(["A"], duplicate_class_names(src))

    def test_no_duplicate_classes_in_tests(self):
        self.assertEqual(
            {},
            scan(TESTS_DIR),
            "同一文件出现重名顶层类（后者覆盖前者，前者用例永不收集）: %s" % scan(TESTS_DIR),
        )


if __name__ == "__main__":
    # 直扫入口（不依赖 unittest 收集，故本文件自身被遮蔽也能拦住）
    sys.exit(main())