"""body 三源（positional / stdin `-` / --body-file）测试：绕开 shell 求值 + 空正文拒绝。

零 herdr 依赖：送达器被 patch 成 returncode=0（push.send_prompt 内部调 subprocess.run）。
日志隔离：COHERD_CONFIG_HOME 指临时目录 + reload(T)/reload(P)（仿 test_push.LogPathTest）。
"""

import importlib
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from typer.testing import CliRunner

from coherd import cli as C
from coherd import push as P
from coherd import tracker as T

ROOT = Path(__file__).resolve().parents[1]

_ENV_KEYS = (
    "HERDR_WORKSPACE_ID",
    "COHERD_ROLE",
    "HERDR_AGENT_NAME",
    "HERDR_PANE_ID",
    "HERDR_SOCKET_PATH",
)


class BodySourceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._saved = {k: os.environ.get(k) for k in _ENV_KEYS}
        for k in _ENV_KEYS:  # 清 env：强制走 --ws/--role 显参，避免自派生撞真实 socket
            os.environ.pop(k, None)
        os.environ["COHERD_CONFIG_HOME"] = str(self.tmp)
        importlib.reload(T)
        importlib.reload(P)
        self.addCleanup(self._restore)
        self.log = self.tmp / "events.log"
        self.runner = CliRunner()
        # 送达器落到 push 模块内的 fake subprocess（只替换 P.subprocess 绑定，
        # 不动全局 subprocess——否则本文件自身的 subprocess.run 也被 mock 掉）
        fake_sub = mock.Mock()
        fake_sub.run.return_value = mock.Mock(returncode=0)
        self._patch = mock.patch.object(P, "subprocess", fake_sub)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def _restore(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.environ.pop("COHERD_CONFIG_HOME", None)
        importlib.reload(T)
        importlib.reload(P)

    def _invoke(self, args: list[str], input_: str | None = None):
        return self.runner.invoke(C.app, args, input=input_)

    def _events(self) -> list[dict]:
        if not self.log.exists():
            return []
        return [json.loads(l) for l in self.log.read_text(encoding="utf-8").splitlines() if l]

    def _args(self, cmd: str, tail: list[str]) -> list[str]:
        return [cmd, "w2p-reviewer", "--ws", "w2p", "--role", "executor", *tail]


class StdinTest(BodySourceTest):
    def test_stdin_body_byte_exact_meta_chars(self):
        """DoD 5：反引号 / $ / ! / 方括号经 stdin 后逐字节一致（不被 shell 求值）。"""
        payload = "a`b$c!d[ef]"
        res = self._invoke(self._args("feedback", ["-"]), input_=payload + "\n")
        self.assertEqual(res.exit_code, 0, res.output)
        ev = self._events()
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["body"], payload)
        self.assertEqual(ev[0]["type"], "feedback")

    def test_stdin_notify_works_too(self):
        payload = "交审 x — 详见 /p/a`b.md"
        res = self._invoke(self._args("notify", ["-"]), input_=payload + "\n")
        self.assertEqual(res.exit_code, 0, res.output)
        ev = self._events()
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["type"], "notify")
        self.assertEqual(ev[0]["body"], payload)

    def test_stdin_multiline_preserved(self):
        res = self._invoke(self._args("feedback", ["-"]), input_="行1\n行2\n")
        self.assertEqual(res.exit_code, 0, res.output)
        self.assertEqual(self._events()[0]["body"], "行1\n行2")  # 只剥末尾单换行

    def test_stdin_empty_raises_no_log(self):
        res = self._invoke(self._args("feedback", ["-"]), input_="  \n\n")
        self.assertEqual(res.exit_code, 1)
        self.assertEqual(self._events(), [])


class BodyFileTest(BodySourceTest):
    def test_body_file_multiline_trailing_newline_stripped(self):
        f = self.tmp / "body.md"
        f.write_text("分派 x\n- DoD: 1\n- DoD: 2\n\n尾段保留\n", encoding="utf-8")
        res = self._invoke(self._args("feedback", ["--body-file", str(f)]))
        self.assertEqual(res.exit_code, 0, res.output)
        self.assertEqual(
            self._events()[0]["body"], "分派 x\n- DoD: 1\n- DoD: 2\n\n尾段保留"
        )

    def test_body_file_dash_means_stdin(self):
        res = self._invoke(self._args("feedback", ["--body-file", "-"]), input_="x`y\n")
        self.assertEqual(res.exit_code, 0, res.output)
        self.assertEqual(self._events()[0]["body"], "x`y")

    def test_missing_body_file_raises(self):
        res = self._invoke(self._args("feedback", ["--body-file", str(self.tmp / "nope")]))
        self.assertEqual(res.exit_code, 1)
        self.assertEqual(self._events(), [])


class MutualExclusionTest(BodySourceTest):
    def test_msg_and_body_file_conflict(self):
        f = self.tmp / "b.md"
        f.write_text("from file", encoding="utf-8")
        res = self._invoke(self._args("feedback", ["from argv", "--body-file", str(f)]))
        self.assertEqual(res.exit_code, 1)
        self.assertIn("互斥", res.output)
        self.assertEqual(self._events(), [])  # 拒发不污染审计

    def test_no_body_source_at_all(self):
        res = self._invoke(self._args("notify", []))
        self.assertEqual(res.exit_code, 1)
        self.assertEqual(self._events(), [])


@unittest.skipUnless(shutil.which("bash"), "需要 bash 验证真实 shell 管道")
class RealShellPipeTest(BodySourceTest):
    """真 shell 管道端到端：证明 stdin 路径不被 shell 求值（fake herdr 在 PATH）。"""

    def test_shell_pipe_body_not_mangled(self):
        fakebin = self.tmp / "bin"
        fakebin.mkdir()
        herdr = fakebin / "herdr"
        herdr.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        herdr.chmod(0o755)
        env = {
            **os.environ,
            "COHERD_CONFIG_HOME": str(self.tmp),
            "PYTHONPATH": str(ROOT / "src"),
            "PATH": f"{fakebin}{os.pathsep}{os.environ.get('PATH', '')}",
        }
        script = (
            "printf 'a`b$c!d[ef]\\n' | "
            f"{sys.executable} -m coherd.cli feedback w2p-reviewer "
            "--ws w2p --role executor -"
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,  # 退出码由下方断言检查，不让 run 直接抛
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ev = self._events()
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["body"], "a`b$c!d[ef]")


if __name__ == "__main__":
    unittest.main()