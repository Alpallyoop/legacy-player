"""Small fixes from the 2026-10-12 audit, section 4: unused endpoints gone, the rescan lock, the server controls no
longer redirecting the whole process's output, the doctor not counting PC as a console, and the storage wording."""
import io
import re
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from launcher.app import LauncherApp
from launcher.consoles import CONSOLES
from tests.test_app_actions import make_app

ROOT = Path(__file__).resolve().parent.parent


class UnusedEndpointsTests(unittest.TestCase):
    def test_endpoints_the_page_never_calls_are_gone(self):
        for name in ("find_games", "private_link", "monitors", "network_check", "dolphin_pads", "engines_scan"):
            self.assertFalse(hasattr(LauncherApp, "api_" + name), name)

    def test_the_helpers_that_are_still_used_inside_remain(self):
        for name in ("_network_check", "_dolphin_pads", "_engines_scan"):
            self.assertTrue(callable(getattr(LauncherApp, name, None)), name)

    def test_unlocked_list_names_each_call_once(self):
        src = (ROOT / "launcher" / "app.py").read_text(encoding="utf-8")
        line = re.search(r"UNLOCKED = frozenset\(\{(.*?)\}\)", src).group(1)
        names = re.findall(r'"(\w+)"', line)
        self.assertEqual(len(names), len(set(names)), [n for n in names if names.count(n) > 1])


class RescanTests(unittest.TestCase):
    def test_rescan_forgets_the_emulator_list_inside_the_scan_lock(self):
        app, _ = make_app()
        held = []
        real = app._forget_emulators

        def spy():
            held.append(app._scan_lock.locked())
            real()
        app._forget_emulators = spy
        app.rescan()
        self.assertEqual([True], held)
        self.assertTrue(LauncherApp.rescan.__doc__ and "games folders" in LauncherApp.rescan.__doc__)


class ServerControlOutputTests(unittest.TestCase):
    def test_cli_writes_to_the_stream_it_is_given(self):
        from server import cli
        with tempfile.TemporaryDirectory() as d:
            args = type("A", (), {"state_dir": Path(d)})()
            out, real = io.StringIO(), io.StringIO()
            with mock.patch.object(sys, "stdout", real):
                self.assertEqual(1, cli.status(args, out=out))
                self.assertEqual(0, cli.stop(args, out=out))
        self.assertEqual("Server is not running.\nServer is not running.\n", out.getvalue())
        self.assertEqual("", real.getvalue())

    def test_cli_still_prints_when_run_from_the_command_line(self):
        from server import cli
        with tempfile.TemporaryDirectory() as d:
            args = type("A", (), {"state_dir": Path(d)})()
            real = io.StringIO()
            with mock.patch.object(sys, "stdout", real):
                cli.status(args)
        self.assertEqual("Server is not running.\n", real.getvalue())

    def test_server_control_leaves_other_threads_output_alone(self):
        from server import cli
        app, _ = make_app()
        seen = {}

        def fake_status(args, out=None):
            seen["stdout"] = sys.stdout          # no process-wide redirect while the call runs
            print("Server is not running.", file=out)
            return 1
        before = sys.stdout
        with mock.patch.object(cli, "status", fake_status):
            result = app.api_server_control({"action": "status"})
        self.assertIs(before, seen["stdout"])
        self.assertEqual("Server is not running.", result["message"])

    def test_no_global_redirects_left_in_the_app(self):
        src = (ROOT / "launcher" / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("redirect_stdout", src)
        self.assertNotIn("redirect_stderr", src)


class ConsoleCountTests(unittest.TestCase):
    def test_pc_is_not_counted_as_a_console(self):
        app, _ = make_app()
        consoles = len([c for c in CONSOLES if c.id != "pc"])
        self.assertEqual(consoles, app.api_home({})["consoles_total"])
        self.assertEqual(consoles, app.api_doctor({})["consoles_total"])
        with mock.patch.object(LauncherApp, "_console_ready", lambda self, cid, found=None: cid == "pc"):
            self.assertEqual((0, consoles), app._console_counts())


class WordingTests(unittest.TestCase):
    def test_storage_total_says_game_or_games(self):
        src = (ROOT / "launcher" / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('" across "+d.total_games+" games"', src)
        self.assertIn('" game"+(d.total_games===1?"":"s")', src)

    def test_contrast_tool_is_quiet_when_everything_passes(self):
        src = (ROOT / "tools" / "contrast_check.py").read_text(encoding="utf-8")
        self.assertIn("if seen:", src)


if __name__ == "__main__":
    unittest.main()
