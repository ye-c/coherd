"""coherd.tracker 单元测试：session 目录平铺布局（sessions/<ws>-<ts>-<pid>/<id>.task.md 等）。

零依赖（stdlib unittest），用 COHERD_CONFIG_HOME 指向临时目录 + importlib.reload(T)
隔离，不触碰真实 ~/.config/coherd/sessions/。
"""

import importlib
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from coherd import tracker as T

WS = "w37"


def make_data(
    task_id: str, status: str = "pending", ws: str = WS, gate: str | None = None
) -> dict:
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
        **({"gate": gate} if gate is not None else {}),
    }


class SessionsDirMixin:
    """把 SESSIONS_DIR 经 COHERD_CONFIG_HOME 指向临时目录（reload 生效），测试隔离。"""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        os.environ["COHERD_CONFIG_HOME"] = self._tmp.name
        importlib.reload(T)
        self.sessions = T.SESSIONS_DIR
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        os.environ.pop("COHERD_CONFIG_HOME", None)
        importlib.reload(T)


class LayoutTest(SessionsDirMixin, unittest.TestCase):
    def test_write_new_flat_session_dir(self):
        p = T.write_new(make_data("w37-20260828084854"))
        # 平铺: session 目录下 <id>.task.md；无固定 task.md / 无 <ws>/<id>.md 分桶
        self.assertEqual(p.name, "w37-20260828084854.task.md")
        self.assertTrue(p.parent.name.startswith("w37-"))
        self.assertTrue(p.is_file())
        self.assertFalse((p.parent / "task.md").exists())
        self.assertFalse((self.sessions / WS / "w37-20260828084854.md").exists())

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


class GateFieldTest(SessionsDirMixin, unittest.TestCase):
    """gate：可选单行门禁命令（不进必填集；格式校验；改状态路径保真）。"""

    TID = "w37-20260828084854"

    def test_gate_roundtrip(self):
        gate = "env -u HERDR_ENV uv run --with pytest pytest -q"
        T.write_new(make_data(self.TID, gate=gate))
        self.assertEqual(T.find_tracker(self.TID)["gate"], gate)

    def test_legacy_record_without_gate_valid(self):
        d = make_data(self.TID)
        self.assertNotIn("gate", d)
        T.validate(d)  # 旧记录缺 gate 合法
        data = T.load(T.write_new(d))
        self.assertEqual(data["gate"], "")

    def test_gate_with_newline_rejected(self):
        with self.assertRaises(ValueError):
            T.write_new(make_data(self.TID, gate="pytest -q\nruff check ."))

    def test_gate_block_marker_rejected(self):
        with self.assertRaises(ValueError):
            T.validate(make_data(self.TID, gate="|"))

    def test_fields_order_stable(self):
        self.assertEqual(
            T.FIELDS,
            (
                "id",
                "ws",
                "created_at",
                "task_name",
                "status",
                "parent_id",
                "parent_spec",
                "objective",
                "dod",
                "output_path",
                "gate",
            ),
        )

    def test_set_status_preserves_single_line_gate(self):
        gate = "env -u HERDR_ENV -u HERDR_SOCKET_PATH uv run --with pytest pytest -q"
        T.write_new(make_data(self.TID, gate=gate))
        T.set_status(self.TID, "done")
        data = T.find_tracker(self.TID)
        self.assertEqual(data["gate"], gate)
        raw = Path(data["_path"]).read_text(encoding="utf-8")
        self.assertIn(f"gate: {gate}\n", raw)  # 逐字节不变，未被块标量改写

    def test_set_status_preserves_pathological_multiline_gate(self):
        """手写非法含换行值绕过 validate：set_status 后解析值等价（空行不丢不并）。"""
        p = T.write_new(make_data(self.TID))
        raw = p.read_text(encoding="utf-8")
        pathological = "pytest -q\n\nruff check ."
        raw = raw.replace(
            "gate: \n",
            "gate: |\n  pytest -q\n  \n  ruff check .\n",
            1,
        )
        p.write_text(raw, encoding="utf-8")
        self.assertEqual(T.load(p)["gate"], pathological)
        T.set_status(self.TID, "active")
        data = T.find_tracker(self.TID)
        self.assertEqual(data["gate"], pathological)
        self.assertEqual(data["status"], "active")


class SessionDirTest(SessionsDirMixin, unittest.TestCase):
    """glob_session_dir: 目录名匹配 <ws>-* 即 session（放宽判定）/ 排除旧裸名目录。"""

    def test_glob_latest_qualified_session(self):
        T.write_new(make_data("w37-20260828084854"))
        first = T.glob_session_dir("w37")
        # 后续第二个启动的 session → 取最新
        later = self.sessions / "w37-20270101000000-99999"
        later.mkdir(parents=True)
        (later / "w37-20270101000000.task.md").write_text(
            (first / "w37-20260828084854.task.md").read_text(), encoding="utf-8"
        )
        self.assertEqual(T.glob_session_dir("w37"), later)
        self.assertNotEqual(first, later)

    def test_glob_counts_legacy_format_dir(self):
        """放宽判定：仅 task.md 固定名、无 *.task.md 平铺文件的旧格式目录（匹配 <ws>-*）同样计入。"""
        legacy = self.sessions / "w37-20260828132220"
        legacy.mkdir(parents=True)
        (legacy / "task.md").write_text("x", encoding="utf-8")
        self.assertEqual(T.glob_session_dir("w37"), legacy)

    def test_glob_excludes_bare_name_dirs(self):
        """目录名不含 <ws>- 前缀（旧裸名目录式 w2y/w32 等）不计入。"""
        T.write_new(make_data("w37-20260828084854"))
        (self.sessions / "w2y").mkdir(parents=True)
        self.assertIsNone(T.glob_session_dir("w2y"))

    def test_find_tracker_across_sessions(self):
        """老 session 任务在最新 session 存在时仍可达（跨 session 搜索）。"""
        p1 = T.write_new(make_data("w37-20260828084854"))
        later = self.sessions / "w37-20270101000000-99999"
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

    def test_new_with_gate_option(self):
        runner, app = self._runner()
        gate = "env -u HERDR_ENV uv run --with pytest pytest -q"
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
                "--gate",
                gate,
            ],
        )
        self.assertEqual(res.exit_code, 0, res.stdout + res.stderr)
        tracks = list(T.glob_session_dir("w37").glob("*.task.md"))
        self.assertEqual(len(tracks), 1)
        self.assertEqual(T.load(tracks[0])["gate"], gate)

    def test_new_gate_newline_rejected(self):
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
                "--gate",
                "pytest -q\nruff check .",
            ],
        )
        self.assertNotEqual(res.exit_code, 0)


if __name__ == "__main__":
    unittest.main()