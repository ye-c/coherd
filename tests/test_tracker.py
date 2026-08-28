"""coherd.tracker 单元测试：扁平布局（一任务一目录 tasks/<id>/task.md 等）。

零依赖（stdlib unittest），用 mock patch T.TASKS_DIR 指向临时目录隔离，
不触碰真实 ~/.config/coherd/tasks/。
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

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
    """把 T.TASKS_DIR 指向临时目录，测试隔离。"""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tasks = Path(self._tmp.name) / "tasks"
        self.patcher = mock.patch.object(T, "TASKS_DIR", self.tasks)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)


class LayoutTest(TasksDirMixin, unittest.TestCase):
    def test_write_new_flat_task_dir(self):
        p = T.write_new(make_data("w37-20260828084854"))
        # 目录名 = id，文件固定名 task.md，无 <ws>/<id>.md 分桶
        self.assertEqual(p, self.tasks / "w37-20260828084854" / "task.md")
        self.assertTrue(p.is_file())
        self.assertFalse((self.tasks / WS / "w37-20260828084854.md").exists())
        # 目录由 write_new 自动 mkdir（不用手动建）
        self.assertTrue(p.parent.is_dir())

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
        self.assertEqual(
            Path(d1["_path"]), self.tasks / "w37-20260828084854" / "task.md"
        )

    def test_find_tracker_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            T.find_tracker("w37-19700101000000")

    def test_load_ws_from_frontmatter(self):
        d = make_data("w37-20260828084854", ws="w2c")
        p = T.write_new(d)
        data = T.load(p)
        # _ws 从 frontmatter ws 字段读，不再取目录名（目录名 = id）
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


class CliListTest(TasksDirMixin, unittest.TestCase):
    """task list 单层 glob 遍历 + frontmatter 过滤。"""

    def _runner(self):
        from typer.testing import CliRunner

        from coherd import cli

        return CliRunner(mix_stderr=False), cli.app

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
        T.write_new(make_data("w37-20260828084854"))
        bad = self.tasks / "w37-bad1" / "task.md"
        bad.parent.mkdir(parents=True)
        bad.write_text("no frontmatter here", encoding="utf-8")
        runner, app = self._runner()
        res = runner.invoke(app, ["task", "list"])
        self.assertEqual(res.exit_code, 0, res.stdout + res.stderr)
        self.assertIn("w37-20260828084854", res.stdout)
        self.assertIn("警告", res.stderr)

    def test_show_and_status_cli(self):
        T.write_new(make_data("w37-20260828084854"))
        runner, app = self._runner()
        res = runner.invoke(app, ["task", "show", "w37-20260828084854"])
        self.assertEqual(res.exit_code, 0, res.stdout + res.stderr)
        self.assertIn("task.md", res.stdout)
        res2 = runner.invoke(
            app, ["task", "status", "w37-20260828084854", "--set", "active"]
        )
        self.assertEqual(res2.exit_code, 0, res2.stdout + res2.stderr)
        data = T.find_tracker("w37-20260828084854")
        self.assertEqual(data["status"], "active")


if __name__ == "__main__":
    unittest.main()