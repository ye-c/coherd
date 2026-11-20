"""守护: 并行扇出前的共享面冻结与并行判定准则。

对应 spec `way-20261120043614-01` AC1-AC5（措辞型纪律机检化, 见 spec D6）。
只做文档措辞断言, 不解析语义:

    PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_contract*.py'
"""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROLES = REPO / "roles"

CONTRACT = ROLES / "CONTRACT.md"
COORDINATOR = ROLES / "coordinator.md"
PLAN_TEMPLATE = ROLES / "templates" / "plan.template.md"
EXECUTOR = ROLES / "executor.md"

# 判据四锚点: 只在唯一权威处出现, 其余位置复述即判红
JUDGE_ANCHORS = ("不看对方产出", "独立跑完", "交集", "停扇出")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(path: Path, heading_prefix: str) -> str:
    """取某个 `## ` 二级标题到下一个 `## ` 之间的正文。"""
    lines = _text(path).splitlines()
    out, hit = [], False
    for line in lines:
        if line.startswith("## "):
            if hit:
                break
            hit = line.startswith(heading_prefix)
            continue
        if hit:
            out.append(line)
    assert hit, "未找到小节: %s" % heading_prefix
    return "\n".join(out)


class SharedSurfaceDefinitionTest(unittest.TestCase):
    """AC1: 契约 §3 含共享面定义 + 并行判据(步骤+默认值) + 冻结三动作 + 白名单局限。"""

    def setUp(self):
        self.sec3 = _section(CONTRACT, "## 3. ")

    def test_ac1_definition_is_marked_as_the_single_authority(self):
        self.assertIn("共享面", self.sec3)
        self.assertIn("本术语定义处", self.sec3)
        self.assertIn("共同依赖", self.sec3)

    def test_ac1_whitelist_cannot_express_dependencies(self):
        self.assertIn("文件白名单", self.sec3)
        self.assertIn("表达不了共享面", self.sec3)

    def test_ac1_parallel_judgement_anchors(self):
        for anchor in JUDGE_ANCHORS[:3]:  # 不看对方产出 / 独立跑完 / 交集
            self.assertIn(anchor, self.sec3, "并行判据缺锚点: %s" % anchor)
        self.assertIn("最小判定步骤", self.sec3)

    def test_ac1_default_is_serial(self):
        self.assertIn("列不全", self.sec3)
        self.assertIn("判串行", self.sec3)

    def test_ac1_freeze_three_actions(self):
        for word in ("定稿", "只读", "停扇出", "重新定稿", "重新扇出"):
            self.assertIn(word, self.sec3, "冻结三动作缺: %s" % word)


class CoordinatorDutyTest(unittest.TestCase):
    """AC2: 协调者文档有拆票并行判定与扇出前定稿、变更停扇出。"""

    def setUp(self):
        self.text = _text(COORDINATOR)

    def test_ac2_parallel_judgement_and_ownership(self):
        for word in ("并行判定", "扇出前", "定稿", "只读", "停扇出", "重新扇出"):
            self.assertIn(word, self.text, "协调者侧缺编排动作: %s" % word)

    def test_ac2_default_value_repeated_for_decision_maker(self):
        self.assertIn("判串行", self.text)


class FreezeListCarrierTest(unittest.TestCase):
    """AC3: 契约硬要求列冻结清单; 模板只有一行提示、无独立小节。"""

    def test_ac3_contract_mandates_freeze_list(self):
        sec3 = _section(CONTRACT, "## 3. ")
        self.assertIn("必须列共享面冻结清单", sec3)
        self.assertIn("多执行者", sec3)

    def test_ac3_template_has_one_line_hint(self):
        text = _text(PLAN_TEMPLATE)
        self.assertIn("共享面冻结清单", text)
        self.assertIn("单执行者免填", text)

    def test_ac3_template_has_no_standalone_section(self):
        headings = [ln for ln in _text(PLAN_TEMPLATE).splitlines() if re.match(r"^#{1,6} ", ln)]
        self.assertFalse(
            [h for h in headings if "共享面" in h],
            "模板不得为冻结清单新增独立小节: %s" % headings,
        )


class WindowChangeRoutingTest(unittest.TestCase):
    """AC4: 窗口内需改共享面 = 漂移回流(需回执) + 不得自改; §4 侧只留一句指针、不复述判据。"""

    def setUp(self):
        self.sec4 = _section(CONTRACT, "## 4. ")

    def test_ac4_drift_channel_is_the_only_way(self):
        self.assertIn("共享面", self.sec4)
        self.assertIn("不得自改", self.sec4)
        self.assertIn("本通道", self.sec4)

    def test_ac4_no_judgement_restatement_in_section4(self):
        for anchor in JUDGE_ANCHORS:
            self.assertNotIn(
                anchor,
                self.sec4,
                "§4 复述了 §3 的判据锚点「%s」= 第二处权威" % anchor,
            )


class SingleExecutorExemptionTest(unittest.TestCase):
    """AC5: 三处改动点均明示 N=1 无负担; 执行者文档不被加重。"""

    def test_ac5_n1_stated_in_all_three_places(self):
        self.assertIn("N=1", _section(CONTRACT, "## 3. "))
        self.assertIn("单执行者跳过", _text(COORDINATOR))
        self.assertIn("单执行者免填", _text(PLAN_TEMPLATE))

    def test_ac5_executor_doc_not_burdened(self):
        text = _text(EXECUTOR)
        self.assertNotIn("并行判定", text)
        self.assertNotIn("共享面冻结", text)


if __name__ == "__main__":
    unittest.main()