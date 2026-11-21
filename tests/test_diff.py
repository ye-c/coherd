"""coherd.diff 单元测试：白名单解析、归属推导、git 改动采集、三分类、CLI 端到端。

密闭性铁律（AGENTS.md「测试必须密闭」）：
  - 宿主 herdr / git 环境变量在 setUpModule 摘净、tearDownModule 原值还原（不是 pop 了事）；
  - COHERD_CONFIG_HOME 指临时目录并 reload(tracker)，绝不读写真实 ~/.config/coherd；
  - git 夹具为临时目录内 `git init` 的真实微型仓库，不依赖宿主仓库状态。
"""

import importlib
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from typer.testing import CliRunner

from coherd import cli as C
from coherd import diff as D
from coherd import tracker as T

HERMETIC_KEYS = (
    "HERDR_SOCKET_PATH",
    "HERDR_WORKSPACE_ID",
    "HERDR_PANE_ID",
    "COHERD_ROLE",
    "HERDR_AGENT_NAME",
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "COHERD_CONFIG_HOME",  # 宿主若已设：与本组同法先存原值再还原（pop 会丢失宿主取值）
)

_host_env: dict[str, str | None] = {}


def setUpModule():
    for k in HERMETIC_KEYS:
        _host_env[k] = os.environ.get(k)
        os.environ.pop(k, None)


def tearDownModule():
    for k, v in _host_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    importlib.reload(T)  # env 已还原，tracker 单例（CONFIG_HOME/SESSIONS_DIR）同步回宿主取值


WS = "wdf"
SPEC = "wdf-spec"
TASK_ID = "wdf-20260101000000"

MULTI_PLAN = """# Plan: 夹具方案

## 1. 现状差异分析

| 缺口 | 现状 | 目标 |
| --- | --- | --- |
| G1 | 手工核对 | 自动核对 |

## 3. 改动文件白名单

| # | 文件 | 类型 | 改动要点 | 归属 |
| --- | --- | --- | --- | --- |
| 1 | `src/one.py` | MOD | 一 | exec-1 |
| 2 | `src/two.py` | MOD | 二 | exec-2 落并修复 |
| 3 | `docs/shared.md` | NEW | 三 | exec-1 起草，exec-2/3 供数 |
| 4 | `docs/shared.md` | NEW | 三（跨行重复） | exec-3 |
| 5 | src/three.py | MOD | 五 | 临时目录声明见附录（无标签） |

## 附录

临时目录 `tmp/` 不纳入白名单（散文声明，非表格）。
"""


class DiffCase(unittest.TestCase):
    """共享夹具：临时 config home + 临时 git 仓库 + 方案/tracker 写入。"""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._saved = {k: os.environ.get(k) for k in HERMETIC_KEYS}
        for k in HERMETIC_KEYS:
            os.environ.pop(k, None)
        os.environ["COHERD_CONFIG_HOME"] = str(self.root / "cfg")
        importlib.reload(T)  # 让 tracker 的 SESSIONS_DIR 指向临时 config home
        self.addCleanup(self._restore_env)
        self.session = T.SESSIONS_DIR / f"{WS}-20260101000000"
        self.session.mkdir(parents=True)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self._git("init", "-q")
        self._git("config", "user.email", "fixture@example.com")
        self._git("config", "user.name", "fixture")

    def _restore_env(self):
        # 逐键还原宿主原值（含 COHERD_CONFIG_HOME，不留空）；reload 使 tracker 回到宿主取值
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        importlib.reload(T)

    # -- 夹具写入 --

    def _git(self, *args: str) -> str:
        p = subprocess.run(
            ["git", *args], cwd=self.repo, capture_output=True, text=True, check=True
        )
        return p.stdout

    def write_plan(self, text: str = MULTI_PLAN, spec: str = SPEC) -> Path:
        p = self.session / f"{spec}.plan.md"
        p.write_text(text, encoding="utf-8")
        return p

    def write_task(self, parent_spec: str = SPEC, task_id: str = TASK_ID) -> Path:
        data = {
            "id": task_id,
            "ws": WS,
            "created_at": "2026-01-01T00:00:00Z",
            "task_name": "夹具任务",
            "status": "pending",
            "parent_spec": parent_spec,
            "objective": "夹具目标",
            "dod": "夹具 DoD",
            "output_path": "src/one.py",
        }
        p = self.session / f"{task_id}.task.md"
        p.write_text(T.render_frontmatter(data), encoding="utf-8")
        return p

    def write_file(self, rel: str, content: str = "x\n") -> Path:
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def commit_all(self, msg: str = "fixture") -> None:
        self._git("add", "-A")
        self._git("commit", "-qm", msg)


class ParseWhitelistTest(DiffCase):
    def test_owner_column_after_file_column_and_compound_expansion(self):
        owners, tags = D.parse_plan_whitelist(MULTI_PLAN)
        self.assertEqual(owners["src/one.py"], {"exec-1"})
        self.assertEqual(owners["src/two.py"], {"exec-2"})  # 散文「落并修复」不入标签
        self.assertEqual(owners["docs/shared.md"], {"exec-1", "exec-2", "exec-3"})  # 跨行并集
        self.assertEqual(owners["src/three.py"], set())  # 无标签单元格
        self.assertEqual(tags, {"exec-1", "exec-2", "exec-3"})

    def test_compact_single_hyphen_separator(self):
        # GFM 紧凑型 `| - |` 分隔线同样成立（旧正则 {3,} 会整表跳过 → 报无白名单表）
        text = "| # | 文件 | 归属 |\n| - | - | - |\n| 1 | `a.py` | exec-1 |\n"
        owners, tags = D.parse_plan_whitelist(text)
        self.assertEqual(owners, {"a.py": {"exec-1"}})
        self.assertEqual(tags, {"exec-1"})

    def test_file_header_alias_and_backtick_wrapped(self):
        # 表头精确白名单：`文件` / `改动文件`，容忍行内代码包裹
        for header_cell in ("文件", "改动文件", "`文件`"):
            with self.subTest(header=header_cell):
                text = (
                    f"| # | {header_cell} | 归属 |\n| --- | --- | --- |\n"
                    "| 1 | `a.py` | exec-1 |\n"
                )
                owners, _ = D.parse_plan_whitelist(text)
                self.assertEqual(owners, {"a.py": {"exec-1"}})

    def test_file_like_header_is_not_whitelist(self):
        # 「参考文件」等含「文件」子串的表头不得被当成白名单（旧子串匹配会吞掉它）
        text = "| 参考文件 | 说明 |\n| --- | --- |\n| `a.py` | 参考 |\n"
        with self.assertRaises(D.DiffError):
            D.parse_plan_whitelist(text)

    def test_file_like_table_skipped_when_real_table_follows(self):
        text = (
            "| 参考文件 | 说明 |\n| --- | --- |\n| `a.py` | 参考 |\n"
            "\n"
            "| # | 文件 | 归属 |\n| - | - | - |\n| 1 | `ok.py` | exec-2 |\n"
        )
        owners, tags = D.parse_plan_whitelist(text)
        self.assertEqual(owners, {"ok.py": {"exec-2"}})
        self.assertEqual(tags, {"exec-2"})

    def test_owner_column_before_file_column(self):
        text = (
            "| # | 归属 | 文件 | 类型 |\n"
            "| --- | --- | --- | --- |\n"
            "| 1 | exec-2 | ` a/b.py ` | MOD |\n"
        )
        owners, tags = D.parse_plan_whitelist(text)
        self.assertEqual(owners, {"a/b.py": {"exec-2"}})
        self.assertEqual(tags, {"exec-2"})

    def test_no_owner_column_yields_empty_tags(self):
        text = "| # | 文件 | 类型 |\n| --- | --- | --- |\n| 1 | `x.py` | NEW |\n"
        owners, tags = D.parse_plan_whitelist(text)
        self.assertEqual(owners, {"x.py": set()})
        self.assertEqual(tags, set())

    def test_first_table_without_file_column_is_skipped(self):
        text = (
            "| 缺口 | 现状 | 目标 |\n| --- | --- | --- |\n| G1 | 手工 | 自动 |\n"
            "\n"
            "| # | 文件 | 归属 |\n| --- | --- | --- |\n| 1 | `ok.py` | exec-1 |\n"
        )
        owners, _ = D.parse_plan_whitelist(text)
        self.assertEqual(list(owners), ["ok.py"])

    def test_missing_whitelist_table_raises(self):
        with self.assertRaises(D.DiffError):
            D.parse_plan_whitelist("# 无表格的方案\n\n临时目录声明见附录。\n")

    def test_non_positive_shapes_ignored(self):
        text = "| # | 文件 | 归属 |\n| --- | --- | --- |\n| 1 | `a.py` | 起草 exec-x，exec-7/9 |\n"
        owners, tags = D.parse_plan_whitelist(text)
        self.assertEqual(owners["a.py"], {"exec-7", "exec-9"})
        self.assertEqual(tags, {"exec-7", "exec-9"})


class ResolveExecutorTest(unittest.TestCase):
    def test_explicit_tag_accepted(self):
        self.assertEqual(D.resolve_target_executor({"exec-1", "exec-2"}, "exec-2"), "exec-2")

    def test_explicit_unknown_tag_rejected_with_list(self):
        with self.assertRaises(D.DiffError) as ctx:
            D.resolve_target_executor({"exec-1", "exec-3"}, "exec-9")
        msg = str(ctx.exception)
        self.assertIn("exec-9", msg)
        self.assertIn("exec-1, exec-3", msg)

    def test_multi_tags_without_explicit_rejected(self):
        with self.assertRaises(D.DiffError):
            D.resolve_target_executor({"exec-1", "exec-2"}, None)

    def test_single_or_empty_tags_defer_to_whole_table(self):
        self.assertIsNone(D.resolve_target_executor({"exec-2"}, None))
        self.assertIsNone(D.resolve_target_executor(set(), None))


class ClassifyTest(unittest.TestCase):
    OWNERS = {
        "src/one.py": {"exec-1"},
        "docs/shared.md": {"exec-1", "exec-2", "exec-3"},
        "src/two.py": {"exec-2"},
    }
    CHANGES = [
        ("M", "src/one.py"),
        ("M", "docs/shared.md"),
        ("M", "src/two.py"),
        ("??", "unexpected.py"),
    ]

    def test_three_groups_no_double_count(self):
        r = D.classify_paths(self.CHANGES, self.OWNERS, "exec-1")
        self.assertEqual([i["path"] for i in r["in_whitelist"]], ["src/one.py", "docs/shared.md"])
        self.assertEqual([i["path"] for i in r["other_domain"]], ["src/two.py"])
        self.assertEqual(r["other_domain"][0]["owners"], {"exec-2"})
        self.assertEqual([i["path"] for i in r["out_of_whitelist"]], ["unexpected.py"])

    def test_single_domain_puts_all_whitelist_hits_in(self):
        owners = {"src/one.py": set(), "src/two.py": set()}
        r = D.classify_paths(self.CHANGES, owners, None)
        self.assertEqual(
            [i["path"] for i in r["in_whitelist"]], ["src/one.py", "src/two.py"]
        )
        self.assertEqual(r["other_domain"], [])
        self.assertEqual([i["path"] for i in r["out_of_whitelist"]], ["docs/shared.md", "unexpected.py"])


class GitChangesTest(DiffCase):
    def test_untracked_nested_leaf_and_spaced_path(self):
        self.write_file("a/b/c.py")
        self.write_file("x y/z.py")
        self.write_file("tracked.py")
        self.commit_all()
        self.write_file("a/b/c.py", "changed\n")
        self.write_file("x y/z.py", "changed\n")
        changes = D.get_git_changes(cwd=self.repo)
        paths = [p for _, p in changes]
        # -uall 穿透未跟踪/嵌套目录至叶子文件；含空格路径不做 C-style 引号转义
        self.assertIn("a/b/c.py", paths)
        self.assertIn("x y/z.py", paths)
        self.assertNotIn("a/b/", paths)
        self.assertNotIn("x y/", paths)

    def test_status_rename_yields_both_paths(self):
        self.write_file("old name.txt")
        self.commit_all()
        self._git("mv", "old name.txt", "new name.txt")
        changes = D.get_git_changes(cwd=self.repo)
        paths = [p for _, p in changes]
        self.assertIn("old name.txt", paths)
        self.assertIn("new name.txt", paths)
        self.assertTrue(all(st.startswith("R") for st, _ in changes))

    def test_base_diff_rename_yields_both_paths(self):
        self.write_file("a.txt")
        self.commit_all()
        base = self._git("rev-parse", "HEAD").strip()
        self._git("mv", "a.txt", "b.txt")
        self.write_file("untracked_new.py")
        changes = D.get_git_changes(base=base, cwd=self.repo)
        paths = [p for _, p in changes]
        self.assertEqual(sorted(paths), ["a.txt", "b.txt"])
        self.assertTrue(changes[0][0].startswith("R"))

    def test_git_invocation_disables_optional_locks(self):
        # 只读核验不得抢 index.lock（否则并发 git commit 取锁失败，CONTRACT §5 实测）
        with mock.patch.object(D.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout=b"")
            D.get_git_changes(cwd=self.repo)
        self.assertEqual(run.call_args.kwargs["env"]["GIT_OPTIONAL_LOCKS"], "0")

    def test_non_repo_raises_diff_error(self):
        with self.assertRaises(D.DiffError):
            D.get_git_changes(cwd=self.root / "not-a-repo")


class CollectTest(DiffCase):
    def setUp(self):
        super().setUp()
        self.write_plan()
        self.write_task()
        self.write_file("src/one.py")
        self.write_file("src/two.py")
        self.write_file("unexpected.py")
        self.commit_all()
        self.write_file("src/one.py", "changed\n")
        self.write_file("src/two.py", "changed\n")
        self.write_file("unexpected.py", "changed\n")
        self.write_file("a/b/c.py")

    def test_collect_classifies_three_groups(self):
        r = D.collect(TASK_ID, executor="exec-1", cwd=self.repo)
        self.assertEqual([i["path"] for i in r["in_whitelist"]], ["src/one.py"])
        self.assertEqual([i["path"] for i in r["other_domain"]], ["src/two.py"])
        self.assertEqual(
            sorted(i["path"] for i in r["out_of_whitelist"]),
            ["a/b/c.py", "unexpected.py"],
        )
        self.assertEqual(r["executor"], "exec-1")
        self.assertEqual(Path(r["plan_path"]).name, f"{SPEC}.plan.md")

    def test_collect_reports_missing_task(self):
        with self.assertRaises(D.DiffError):
            D.collect("wdf-20990101000000", executor="exec-1", cwd=self.repo)

    def test_collect_reports_missing_parent_spec(self):
        self.write_task(parent_spec="", task_id="wdf-20260101000009")
        with self.assertRaises(D.DiffError) as ctx:
            D.collect("wdf-20260101000009", executor="exec-1", cwd=self.repo)
        self.assertIn("parent_spec", str(ctx.exception))

    def test_collect_reports_missing_plan_file(self):
        self.write_task(parent_spec="wdf-absent", task_id="wdf-20260101000010")
        with self.assertRaises(D.DiffError) as ctx:
            D.collect("wdf-20260101000010", executor="exec-1", cwd=self.repo)
        self.assertIn("方案文件不存在", str(ctx.exception))

    def test_collect_reports_unknown_executor(self):
        with self.assertRaises(D.DiffError) as ctx:
            D.collect(TASK_ID, executor="exec-9", cwd=self.repo)
        self.assertIn("exec-9", str(ctx.exception))

    def test_single_owner_plan_needs_no_executor(self):
        self.write_plan(
            "| # | 文件 | 类型 |\n| --- | --- | --- |\n"
            "| 1 | `src/one.py` | MOD |\n| 2 | `src/two.py` | NEW |\n"
        )
        r = D.collect(TASK_ID, cwd=self.repo)
        self.assertIsNone(r["executor"])
        self.assertIn("src/one.py", [i["path"] for i in r["in_whitelist"]])
        self.assertEqual(r["other_domain"], [])
        self.assertIn("unexpected.py", [i["path"] for i in r["out_of_whitelist"]])


class CliTest(DiffCase):
    def setUp(self):
        super().setUp()
        self.write_plan()
        self.write_task()
        self.write_file("src/one.py")
        self.commit_all()
        self.write_file("src/one.py", "changed\n")
        self.write_file("unexpected.py")
        self._cwd = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, self._cwd)
        self.runner = CliRunner()

    def test_cli_exit_zero_with_judgment_free_report(self):
        result = self.runner.invoke(C.app, ["diff", TASK_ID, "--executor", "exec-1"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("[白名单内] (1)", result.output)
        self.assertIn("[他人域内] (0)", result.output)
        self.assertIn("[白名单外] (1)", result.output)
        low = result.output.lower()
        for word in ("approve", "revise", "pass", "fail", "通过", "退回", "警告"):
            self.assertNotIn(word, low)

    def test_cli_paths_flag_is_redundant(self):
        plain = self.runner.invoke(C.app, ["diff", TASK_ID, "--executor", "exec-1"])
        with_paths = self.runner.invoke(
            C.app, ["diff", TASK_ID, "--paths", "--executor", "exec-1"]
        )
        self.assertEqual(plain.exit_code, 0)
        self.assertEqual(plain.output, with_paths.output)

    def test_cli_unknown_executor_exits_nonzero(self):
        result = self.runner.invoke(C.app, ["diff", TASK_ID, "--executor", "exec-9"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("exec-9", result.output)

    def test_cli_missing_task_exits_nonzero(self):
        result = self.runner.invoke(C.app, ["diff", "wdf-20990101000000"])
        self.assertNotEqual(result.exit_code, 0)


if __name__ == "__main__":
    unittest.main()
