"""守护: 外部事实检索的授权入口与阻塞求助通道（措辞型条款机检化）。

对应 tracker `wb3-20261121015043-01` DoD 1-4（四条约束各一条断言，锚点用短语不复制整句：
合法微调措辞不应转红，删条款/改语义必须转红）。只查文档措辞，不解析语义：

    PYTHONPATH=src .venv/bin/python3 -m unittest tests.test_contract_search -q
"""

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROLES = REPO / "roles"


def _read(name: str) -> str:
    return (ROLES / name).read_text(encoding="utf-8")


def _section(doc: str, heading: str) -> str:
    """取 `## <heading>` 起到下一个二级标题前的正文（找不到标题即失败）。"""
    lines = doc.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(heading))
    end = next(
        (j for j in range(start + 1, len(lines)) if lines[j].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _table_row(table_text: str, first_cell: str) -> str:
    """取表格中首列等于 first_cell 的行（找不到即失败）。"""
    needle = f"| {first_cell} |"
    return next(ln for ln in table_text.splitlines() if ln.startswith(needle))


class DispatchBoundaryAuthorizationTest(unittest.TestCase):
    """DoD1: §3 分派模板「边界」是检索授权的入口，且默认禁查。"""

    def test_boundary_field_carries_search_authorization_and_default_deny(self):
        sec3 = _section(_read("CONTRACT.md"), "## 3.")
        self.assertIn("允许检索:", sec3)
        self.assertIn("未写=默认禁查", sec3)


class ExecutorSearchBlockingTest(unittest.TestCase):
    """DoD2: executor 缺外部事实时走 notify 求助（代查或追加授权），不自行发散。"""

    def test_missing_external_facts_routes_to_notify_delegation(self):
        sec = _section(_read("executor.md"), "## 阻塞上报与漂移回流")
        self.assertIn("缺外部事实", sec)
        self.assertIn("代查", sec)


class BlockingTaxonomyTest(unittest.TestCase):
    """DoD2 补强: 检索求助必须在唯一权威（§7 D10）里有归属, 且角色文档不再用计数标签自相矛盾。"""

    def test_d10_assigns_search_help_to_notify_branch(self):
        sec7 = _section(_read("CONTRACT.md"), "## 7.")
        self.assertIn("检索求助", sec7)

    def test_executor_blocking_section_drops_counting_labels(self):
        sec = _section(_read("executor.md"), "## 阻塞上报与漂移回流")
        self.assertNotIn("二分", sec)
        self.assertNotIn("三分", sec)


class SimpleDevAuthorityTest(unittest.TestCase):
    """DoD3: CONTRACT-simple 的 dev 行指向 CONTRACT §5 executor 行，不再自留一份答案。"""

    def test_dev_row_points_at_single_authority(self):
        sec5 = _section(_read("CONTRACT-simple.md"), "## 5.")
        row = _table_row(sec5, "dev")
        self.assertIn("CONTRACT.md", row)
        self.assertIn("executor 行", row)

    def test_simple_dispatch_exposes_search_authorization_entry(self):
        # §5 dev 行指向 CONTRACT §5 executor 行（要求 §3 授权）→ simple §3 必须给出同款入口，否则悬空
        sec3 = _section(_read("CONTRACT-simple.md"), "## 3.")
        self.assertIn("允许检索:", sec3)
        self.assertIn("未写=默认禁查", sec3)

    def test_dev_blocking_has_search_delegation(self):
        # dev.md 阻塞节对齐 executor.md，具备检索求助通道
        sec = _section(_read("dev.md"), "## H3 — 单对象上报")
        self.assertIn("缺外部事实", sec)
        self.assertIn("代查或追加授权", sec)

    def test_dev_row_does_not_reenumerate_tool_set(self):
        # 反向守护：把工具集重新抄回 dev 行 = 事实源漂移复现，必须转红
        sec5 = _section(_read("CONTRACT-simple.md"), "## 5.")
        row = _table_row(sec5, "dev")
        self.assertNotIn("完整代码编辑与运行工具", row)


class ExecutorWhitelistRowTest(unittest.TestCase):
    """DoD4: §5 executor 行的禁止列承载发散检索禁令，允许列只留授权并指回定义处。"""

    def test_executor_row_forbids_divergent_search_with_explicit_authorization(self):
        sec5 = _section(_read("CONTRACT.md"), "## 5.")
        row = _table_row(sec5, "executor")
        self.assertIn("显式授权除外", row)

    def test_executor_row_points_at_authorization_shape_and_scenarios(self):
        # executor 的判据是「有无授权」→ 授权形态指回 §3；场景清单归 coordinator（reviewer 章节不是自己的判据）
        sec5 = _section(_read("CONTRACT.md"), "## 5.")
        row = _table_row(sec5, "executor")
        self.assertIn("§3", row)
        self.assertIn("coordinator.md", row)

    def test_coordinator_marks_definition_place(self):
        # coordinator.md Step 0 显式标明为场景定义处
        sec = _section(_read("coordinator.md"), "## spec 环节")
        self.assertIn("主动调研（定义处）", sec)


if __name__ == "__main__":
    unittest.main()
