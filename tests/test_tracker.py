"""coherd.tracker 单元测试：session 目录平铺布局（tasks/<ws>-<ts>-<pid>/<id>.task.md 等）。

零依赖（stdlib unittest），用 COHERD_CONFIG_HOME 指向临时目录 + importlib.reload(T)
隔离，不触碰真实 ~/.config/coherd/tasks/。
"""

import importlib
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from coherd import tracker as T

WS = "w37"


def make_data(task_id: str, status: str = "pending", ws: str = WS) -> dict:
    return {
        "id": task_id,
        "ws": ws,
        "created_at": "2026-08-28T00:00:00Z",
        "task_name": f"任务-{task_id}",
        "status": status,
        "parent_id": "",
        "objective": "目标",
        "dod": "DoD",
        "output_path": "out.md",
    }


class TasksDirMixin:
    """把 TASKS_DIR 经 COHERD_CONFIG_HOME 指向临时目录（reload 生效），测试隔离。"""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        os.environ["COHERD_CONFIG_HOME"] = self._tmp.name
        importlib.reload(T)
        self.tasks = T.TASKS_DIR
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        os.environ.pop("COHERD_CONFIG_HOME", None)
        importlib.reload(T)


class LayoutTest(TasksDirMixin, unittest.TestCase):
    def test_write_new_flat_session_dir(self):
        p = T.write_new(make_data("w37-20260828084854"))
        # 平铺: session 目录下 <id>.task.md；无固定 task.md / 无 <ws>/<id>.md 分桶
        self.assertEqual(p.name, "w37-20260828084854.task.md")
        self.assertTrue(p.parent.name.startswith("w37-"))
        self.assertTrue(p.is_file())
        self.assertFalse((p.parent / "task.md").exists())
        self.assertFalse((self.tasks / WS / "w37-20260828084854.md").exists())

    def test_write_new_reuses_latest_session(self):
        p1 = T.write_new(make_data("w37-20260828084854"))
        p2 = T.write_new(make_data("w37-20260828091158"))
        self.assertEqual(p1.parent, p2.parent)

    def test_write_new_dup_raises(self):
        d = make_data("w37-20260828084854")
        T.write_new(d)
        with self.assertRaises(FileExistsError):
            T.write_new(d)

    def test_find_tracker_cross_id(self):
        T.write_new(make_data("w37-20260828084854", ws="w37"))
        T.write_new(make_data("w2c-202608260001", ws="w2c"))
        d1 = T.find_tracker("w37-20260828084854")
        d2 = T.find_tracker("w2c-202608260001")
        self.assertEqual(d1["ws"], "w37")
        self.assertEqual(d2["ws"], "w2c")
        self.assertEqual(Path(d1["_path"]).name, "w37-20260828084854.task.md")

    def test_find_tracker_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            T.find_tracker("w37-19700101000000")

    def test_load_ws_from_frontmatter(self):
        d = make_data("w37-20260828084854", ws="w2c")
        p = T.write_new(d)
        data = T.load(p)
        # _ws 从 frontmatter ws 字段读，不再从目录名取
        self.assertEqual(data["_ws"], "w2c")

    def test_set_status_roundtrip(self):
        T.write_new(make_data("w37-20260828084854"))
        T.set_status("w37-20260828084854", "done")
        data = T.find_tracker("w37-20260828084854")
        self.assertEqual(data["status"], "done")

    def test_set_status_invalid_raises(self):
        T.write_new(make_data("w37-20260828084854"))
        with self.assertRaises(ValueError):
            T.set_status("w37-20260828084854", "bogus")

    def test_archive_removed(self):
        self.assertFalse(hasattr(T, "ARCHIVE_DIR"))


class SessionDirTest(TasksDirMixin, unittest.TestCase):
    """glob_session_dir: 最新合格 session / 排除旧存量。"""

    def test_glob_latest_qualified_session(self):
        T.write_new(make_data("w37-20260828084854"))
        first = T.glob_session_dir("w37")
        # 后续第二个启动的 session（内含任务）→ 取最新
        later = self.tasks / "w37-20270101000000-99999"
        later.mkdir(parents=True)
        (later / "w37-20270101000000.task.md").write_text(
            (first / "w37-20260828084854.task.md").read_text(), encoding="utf-8"
        )
        self.assertEqual(T.glob_session_dir("w37"), later)
        self.assertNotEqual(first, later)

    def test_glob_excludes_empty_and_legacy_dirs(self):
        T.write_new(make_data("w37-20260828084854"))
        session = T.glob_session_dir("w37")
        # 空目录（旧存量 w2y-* 式）不计入
        (self.tasks / "w2y-20260101000000-111").mkdir(parents=True)
        self.assertIsNone(T.glob_session_dir("w2y"))
        # 旧子目录式（dir/task.md 固定名，非 *.task.md）不计入
        legacy = self.tasks / "w37-20260828132220"
        legacy.mkdir()
        (legacy / "task.md").write_text("x", encoding="utf-8")
        self.assertEqual(T.glob_session_dir("w37"), session)

    def test_find_tracker_across_sessions(self):
        """老 session 任务在最新 session 存在时仍可达（跨 session 搜索）。"""
        p1 = T.write_new(make_data("w37-20260828084854"))
        later = self.tasks / "w37-20270101000000-99999"
        later.mkdir(parents=True)
        (later / "w37-20270101000000.task.md").write_text(
            (p1.parent / p1.name).read_text(), encoding="utf-8"
        )
        # 老 session 的历史任务（模拟存量）
        old = p1.parent / "w37-20150101000000.task.md"
        old.write_text((p1.parent / p1.name).read_text(), encoding="utf-8")
        data = T.find_tracker("w37-20150101000000")
        self.assertEqual(data["_path"], str(old))


    def _runner(self):
        from typer.testing import CliRunner

        from coherd import cli

        try:
            return CliRunner(mix_stderr=False), cli.app  # 新 typer/click
        except TypeError:
            return CliRunner(), cli.app  # 旧 typer 不支持 mix_stderr

    def _output(self, res) -> str:
        """合并 stdout/stderr（旧 typer 无独立 stderr 缓冲）。"""
        out = res.stdout
        try:
            out += res.stderr
        except AttributeError:
            pass
        return out

    def test_list_flat_glob_and_ws_filter(self):
        T.write_new(make_data("w37-20260828084854", ws="w37"))
        T.write_new(make_data("w37-20260828091158", ws="w37", status="done"))
        T.write_new(make_data("w2c-202608260001", ws="w2c"))
        runner, app = self._runner()
        res = runner.invoke(app, ["task", "list", "--ws", "w37"])
        self.assertEqual(res.exit_code, 0, res.stdout + res.stderr)
        self.assertIn("w37-20260828084854", res.stdout)
        self.assertIn("w37-20260828091158", res.stdout)
        self.assertNotIn("w2c-202608260001", res.stdout)

    def test_list_status_filter(self):
        T.write_new(make_data("w37-20260828084854", ws="w37"))
        T.write_new(make_data("w37-20260828091158", ws="w37", status="done"))
        runner, app = self._runner()
        res = runner.invoke(app, ["task", "list", "--status", "done"])
        self.assertEqual(res.exit_code, 0, res.stdout + res.stderr)
        self.assertIn("w37-20260828091158", res.stdout)
        self.assertNotIn("w37-20260828084854", res.stdout)

    def test_list_skips_malformed_with_warning(self):
        p = T.write_new(make_data("w37-20260828084854"))
        bad = p.parent / "w37-malformed.task.md"
        bad.write_text("no frontmatter here", encoding="utf-8")
        runner, app = self._runner()
        res = runner.invoke(app, ["task", "list"])
        self.assertEqual(res.exit_code, 0, self._output(res))
        self.assertIn("w37-20260828084854", res.stdout)
        self.assertIn("警告", self._output(res))

    def test_new_creates_session_dir_when_none(self):
        runner, app = self._runner()
        res = runner.invoke(
            app,
            [
                "task",
                "new",
                "--task-name",
                "t1",
                "--objective",
                "o",
                "--dod",
                "d",
                "--output",
                "out.md",
                "--ws",
                "w37",
            ],
        )
        self.assertEqual(res.exit_code, 0, res.stdout + res.stderr)
        self.assertIn("已创建 tracker", res.stdout)
        self.assertIsNotNone(T.glob_session_dir("w37"))

    def test_show_and_status_cli(self):
        T.write_new(make_data("w37-20260828084854"))
        runner, app = self._runner()
        res = runner.invoke(app, ["task", "show", "w37-20260828084854"])
        self.assertEqual(res.exit_code, 0, res.stdout + res.stderr)
        self.assertIn(".task.md", res.stdout)
        res2 = runner.invoke(
            app, ["task", "status", "w37-20260828084854", "--set", "active"]
        )
        self.assertEqual(res2.exit_code, 0, res2.stdout + res2.stderr)
        data = T.find_tracker("w37-20260828084854")
        self.assertEqual(data["status"], "active")


if __name__ == "__main__":
    unittest.main()