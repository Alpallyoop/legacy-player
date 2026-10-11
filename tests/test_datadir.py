"""Legacy Player keeps all its files in its own folder or one the player picks (launcher/datadir.py and its users)."""
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from launcher import datadir, selfuninstall, selfupdate

ROOT = Path(__file__).resolve().parent.parent


def text(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.program = self.tmp / "LegacyPlayer"
        self.program.mkdir()
        self.home = self.tmp / "home"
        self.home.mkdir()


class ResolverOrder(Tmp):
    def resolve(self, arg=None, frozen=True):
        return datadir.resolve(arg, program=self.program, home=self.home, is_frozen=frozen)

    def test_the_default_is_inside_the_program_folder(self):
        r = self.resolve()
        self.assertEqual(("default", self.program / "LegacyPlayerData"), (r.source, r.folder))
        self.assertEqual(self.program / "data", self.resolve(frozen=False).folder)       # a git checkout: <checkout>/data

    def test_argument_beats_pointer_beats_default(self):
        (self.program / "LegacyPlayerData").mkdir()
        (self.program / "LegacyPlayerData" / "user_data.json").write_text("{}")
        chosen = self.tmp / "chosen"
        datadir.write_pointer(chosen, self.program)
        self.assertEqual(("pointer", chosen), (self.resolve().source, self.resolve().folder))
        arg = self.tmp / "arg"
        self.assertEqual(("argument", arg), (self.resolve(arg).source, self.resolve(arg).folder))
        datadir.write_pointer(None, self.program)
        self.assertEqual("default", self.resolve().source)

    def test_pointer_file_is_one_line_and_may_be_relative_or_quoted(self):
        (self.program / "data-location.txt").write_text('"D:\\Games\\LP"\r\n', encoding="utf-8-sig")
        if os.name == "nt":
            self.assertEqual(Path("D:\\Games\\LP"), self.resolve().folder)
        (self.program / "data-location.txt").write_text("mine\n", encoding="utf-8")
        self.assertEqual(self.program / "mine", self.resolve().folder)
        (self.program / "data-location.txt").write_text("\n", encoding="utf-8")
        self.assertEqual("default", self.resolve().source)                                # blank: ignored

    def test_old_home_folder_is_used_for_now_and_offered_to_move(self):
        old = self.home / ".legacy-player"
        old.mkdir()
        (old / "user_data.json").write_text("{}")
        r = self.resolve()
        self.assertEqual(("legacy", old, old), (r.source, r.folder, r.legacy))
        (self.program / "LegacyPlayerData").mkdir()
        (self.program / "LegacyPlayerData" / "user_data.json").write_text("{}")
        self.assertEqual("default", self.resolve().source)                                # the new place wins once used

    def test_an_unwritable_program_folder_asks(self):
        with mock.patch.object(datadir, "writable", return_value=False):
            r = self.resolve()
        self.assertEqual(("choose", None), (r.source, r.folder))

    def test_the_launcher_asks_for_a_folder_and_remembers_it(self):
        from launcher import __main__ as entry
        picked = self.tmp / "picked"
        with mock.patch.object(datadir, "resolve", return_value=datadir.Resolution(None, "choose", self.program, self.program / "LegacyPlayerData")), \
             mock.patch.object(datadir, "message_box"):
            where = entry.choose_data_folder(None, True, picker=lambda *a, **k: {"path": str(picked)})
            self.assertEqual(picked, where.folder)
            self.assertEqual(picked, datadir.read_pointer(self.program))
            self.assertIsNone(entry.choose_data_folder(None, True, picker=lambda *a, **k: {"path": ""}))
            self.assertIsNone(entry.choose_data_folder(None, False))                    # no window: no guessing

    def test_no_default_in_the_users_home(self):
        src = text("launcher/__main__.py")
        self.assertNotIn("Path.home()", src)
        self.assertNotIn(".legacy-player", src)
        self.assertNotIn("LOCALAPPDATA", text("legacy_player_app.py"))


class Logs(Tmp):
    def test_default_and_chosen_logs_folder(self):
        data = self.tmp / "data"
        data.mkdir()
        self.assertEqual(data / "logs", datadir.logs_folder(data))
        (data / "logs").mkdir()
        (data / "logs" / "app.log").write_text("old lines\n")
        elsewhere = self.tmp / "mylogs"
        datadir.set_logs_folder(data, elsewhere)
        self.assertEqual(elsewhere, datadir.logs_folder(data))
        datadir.tidy_logs(data, old_app_folder=self.tmp / "none")                        # the next start moves them
        self.assertEqual("old lines\n", (elsewhere / "app.log").read_text())
        self.assertFalse((data / "logs").exists())
        datadir.set_logs_folder(data, None)
        self.assertEqual(data / "logs", datadir.logs_folder(data))
        self.assertFalse((data / datadir.LOGS_POINTER_NAME).exists())

    def test_old_scattered_logs_are_gathered(self):
        data = self.tmp / "data"
        for rel in ("launcher.log", "server/server.log", "social/service.log", "update/apply.log", "reports/r1.json"):
            (data / rel).parent.mkdir(parents=True, exist_ok=True)
            (data / rel).write_text(rel)
        old_app = self.tmp / "LocalAppData" / "LegacyPlayer"
        old_app.mkdir(parents=True)
        (old_app / "app.log").write_text("from the old exe\n")
        logs = datadir.tidy_logs(data, old_app_folder=old_app)
        for name in ("launcher.log", "server.log", "service.log", "apply.log"):
            self.assertTrue((logs / name).is_file(), name)
        self.assertTrue((logs / "reports" / "r1.json").is_file())
        self.assertIn("from the old exe", (logs / "app.log").read_text())
        self.assertFalse(old_app.exists())                                               # the folder older versions made is gone

    def test_a_foreign_folder_with_more_than_app_log_is_left_alone(self):
        old_app = self.tmp / "OldAppFolder"
        old_app.mkdir()
        (old_app / "app.log").write_text("x")
        (old_app / "something.else").write_text("y")
        datadir.tidy_logs(self.tmp / "data", old_app_folder=old_app)
        self.assertTrue((old_app / "something.else").exists())
        self.assertTrue((old_app / "app.log").exists())

    def test_the_app_routes_its_logs(self):
        from launcher.app import LauncherApp
        data = self.tmp / "data"
        logs = self.tmp / "logs-here"
        data.mkdir()
        datadir.set_logs_folder(data, logs)
        app = LauncherApp(data)
        self.assertEqual(logs, app.logs_dir)
        self.assertEqual(logs / "reports", app.reports.dir)
        self.assertEqual(logs / "service.log", app.social_host.log)
        self.assertEqual(logs, app.self_update.logs_dir)
        self.assertEqual(logs / "server.log", app._server_args(False).log_file)

    def test_the_server_writes_its_log_where_it_is_told(self):
        from server import cli
        src = text("server/cli.py")
        self.assertIn('getattr(args, "log_file", None)', src)

    def test_the_windowed_exe_logs_into_the_data_folder(self):
        import legacy_player_app
        data = self.tmp / "d"
        with mock.patch.object(sys, "stdout", None), mock.patch.object(sys, "stderr", None), \
             mock.patch.object(sys, "argv", ["LegacyPlayer.exe", "--data-dir", str(data)]):
            legacy_player_app._fix_stdio()
            print("hello log")
            stream = sys.stdout
            stream.flush()
            stream.close()
        self.assertIn("hello log", (data / "logs" / "app.log").read_text(encoding="utf-8"))


class TempFiles(Tmp):
    def test_tempdir_is_inside_the_data_folder_and_cleaned_at_start(self):
        data = self.tmp / "data"
        (data / "tmp" / "old").mkdir(parents=True)
        (data / "tmp" / "old" / "f").write_text("x")
        (data / "tmp" / "lp-firewall.cmd").write_text("x")
        saved = (tempfile.tempdir, {k: os.environ.get(k) for k in ("TEMP", "TMP", "TMPDIR")})
        try:
            tmp = datadir.setup_tempdir(data)
            self.assertEqual([], list(tmp.iterdir()))
            self.assertEqual(str(data / "tmp"), tempfile.gettempdir())
            self.assertEqual(str(data / "tmp"), os.environ["TEMP"])
            d = Path(tempfile.mkdtemp(prefix="lp-firewall-"))                            # what firewall.py does
            self.assertEqual(data / "tmp", d.parent)
        finally:
            tempfile.tempdir = saved[0]
            for k, v in saved[1].items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class Moving(Tmp):
    def make_old(self):
        old = self.home / ".legacy-player"
        (old / "emulators" / "duckstation").mkdir(parents=True)
        (old / "emulators" / "duckstation" / "duckstation.exe").write_bytes(b"MZ" * 100)
        (old / "saves" / "nes").mkdir(parents=True)
        (old / "saves" / "nes" / "a.srm").write_bytes(b"\0" * 8192)
        (old / "window_profile").mkdir()
        (old / "window_profile" / "Cookies").write_text("locked by the browser")
        (old / "instance.lock").write_text("")
        exe = str(old / "emulators" / "duckstation" / "duckstation.exe")
        (old / "user_data.json").write_text(json.dumps({
            "emulator_paths": {"duckstation": exe, "dolphin": "D:\\Dolphin\\Dolphin.exe"},
            "save_root": str(old / "saves"), "roots": ["D:\\Games"]}))
        return old, exe

    def test_copy_verify_rewrite_then_remove_on_next_start(self):
        old, exe = self.make_old()
        new = self.program / "LegacyPlayerData"
        out = datadir.move_data(old, new, program=self.program, default=new, lister=lambda: [])
        self.assertEqual(str(new), out["to"])
        self.assertTrue((new / "saves" / "nes" / "a.srm").is_file())
        self.assertFalse((new / "window_profile").exists())                              # in use by the open window; made again
        self.assertFalse((new / "instance.lock").exists())
        ud = json.loads((new / "user_data.json").read_text())
        self.assertEqual(str(new / "emulators" / "duckstation" / "duckstation.exe"), ud["emulator_paths"]["duckstation"])
        self.assertEqual("D:\\Dolphin\\Dolphin.exe", ud["emulator_paths"]["dolphin"])      # outside: untouched
        self.assertEqual(str(new / "saves"), ud["save_root"])
        self.assertEqual(["D:\\Games"], ud["roots"])
        self.assertTrue(old.exists())                                                    # still in use until the restart
        self.assertIsNone(datadir.read_pointer(self.program))                            # the default needs no pointer
        done = datadir.finish_pending_move(new, lister=lambda: [])
        self.assertTrue(done["removed"])
        self.assertFalse(old.exists())
        self.assertFalse((new / datadir.MOVED_MARKER).exists())

    def test_a_picked_folder_is_remembered_next_to_the_program(self):
        old, _ = self.make_old()
        picked = self.tmp / "D" / "Legacy"
        datadir.move_data(old, picked, program=self.program, lister=lambda: [])
        self.assertEqual(picked, datadir.read_pointer(self.program))
        self.assertEqual("pointer", datadir.resolve(program=self.program, home=self.home, is_frozen=True).source)

    def test_never_while_a_program_runs_from_the_old_folder(self):
        old, exe = self.make_old()
        with self.assertRaises(datadir.MoveError) as cm:
            datadir.move_data(old, self.tmp / "new", program=self.program, lister=lambda: [(99999, exe)])
        self.assertIn("duckstation.exe", str(cm.exception))
        self.assertFalse((self.tmp / "new").exists())
        new = self.tmp / "new2"
        datadir.move_data(old, new, program=self.program, lister=lambda: [])
        out = datadir.finish_pending_move(new, lister=lambda: [(99999, exe)])
        self.assertFalse(out["removed"])
        self.assertTrue(old.exists())                                                    # waits for the next start
        self.assertTrue((new / datadir.MOVED_MARKER).exists())

    def test_a_bad_copy_changes_nothing(self):
        old, _ = self.make_old()
        new = self.tmp / "new"
        with mock.patch.object(datadir, "verify_copy", return_value=["saves/nes/a.srm differs"]):
            with self.assertRaises(datadir.MoveError):
                datadir.move_data(old, new, program=self.program, lister=lambda: [])
        self.assertFalse(new.exists())
        self.assertIsNone(datadir.read_pointer(self.program))
        self.assertTrue((old / "user_data.json").exists())

    def test_verify_notices_a_missing_or_short_file(self):
        old, _ = self.make_old()
        new = self.tmp / "copy"
        datadir.copy_tree(old, new)
        self.assertEqual([], datadir.verify_copy(old, new))
        (new / "saves" / "nes" / "a.srm").write_bytes(b"\0")
        (new / "user_data.json").unlink()
        self.assertEqual(2, len(datadir.verify_copy(old, new)))

    def test_a_full_folder_gets_its_own_subfolder_and_overlaps_are_refused(self):
        old, _ = self.make_old()
        busy = self.tmp / "Games"
        busy.mkdir()
        (busy / "mario.nes").write_text("x")
        self.assertEqual(busy / "LegacyPlayerData", datadir.choose_target(old, busy))
        with self.assertRaises(datadir.MoveError):
            datadir.choose_target(old, old / "inside")
        with self.assertRaises(datadir.MoveError):
            datadir.choose_target(old, Path("relative"))

    def test_the_old_folder_is_not_removed_when_it_is_not_ours(self):
        new = self.tmp / "new"
        new.mkdir()
        stranger = self.tmp / "stranger"
        stranger.mkdir()
        (stranger / "thesis.docx").write_text("x")
        (new / datadir.MOVED_MARKER).write_text(json.dumps({"from": str(stranger)}))
        out = datadir.finish_pending_move(new, lister=lambda: [])
        self.assertTrue((stranger / "thesis.docx").exists())
        self.assertFalse(out["removed"])

    def test_rewrite_value_matches_whole_folder_names_only(self):
        old = str(Path("/x/.legacy-player"))
        new = str(Path("/y/LegacyPlayerData"))
        self.assertEqual(str(Path(new) / "a" / "b.exe"), datadir.rewrite_value(old + os.sep + "a" + os.sep + "b.exe", old, new))
        self.assertEqual(old + "-backup/x", datadir.rewrite_value(old + "-backup/x", old, new))
        self.assertEqual(new, datadir.rewrite_value(old, old, new))
        self.assertEqual({"k": [5, None, True]}, datadir.rewrite_value({"k": [5, None, True]}, old, new))


class AppEndpoints(Tmp):
    def app(self):
        from launcher.app import LauncherApp
        data = self.tmp / "data"
        return LauncherApp(data), data

    def test_picker_endpoint_runs_without_the_lock_and_returns_the_path(self):
        from launcher.app import LauncherApp
        self.assertIn("pick_path", LauncherApp.UNLOCKED)
        self.assertNotIn("data_folder", LauncherApp.UNLOCKED)
        app, _ = self.app()
        seen = {}

        def fake(kind, title, initial, exe_only=False):
            seen.update(kind=kind, exe=exe_only)
            return {"available": True, "cancelled": False, "path": "C:\\Emu\\duckstation.exe"}
        with mock.patch.object(datadir, "pick", fake):
            out = app.api_pick_path({"kind": "file", "exe": True, "title": "x"})
        self.assertEqual("C:\\Emu\\duckstation.exe", out["path"])
        self.assertEqual({"kind": "file", "exe": True}, seen)

    def test_windows_picker_uses_a_real_dialog_and_passes_text_safely(self):
        calls = []

        class Done:
            returncode, stdout, stderr = 0, "noise PICKED:D:\\Legacy Player\n".encode(), b""
        out = datadir.pick("folder", 'Pick "here"; rm -rf', "C:\\x", runner=lambda cmd, **kw: calls.append((cmd, kw)) or Done(),
                           platform="win32")
        self.assertEqual("D:\\Legacy Player", out["path"])
        cmd, kw = calls[0]
        self.assertIn("-STA", cmd)
        self.assertIn("FolderBrowserDialog", cmd[-1])
        self.assertIn("OpenFileDialog", cmd[-1])
        self.assertNotIn("rm -rf", " ".join(cmd))                                       # the title travels in the environment
        self.assertEqual('Pick "here"; rm -rf', kw["env"]["LP_PICK_TITLE"])

        class Cancelled:
            returncode, stdout, stderr = 1, b"", b""
        self.assertTrue(datadir.pick("file", runner=lambda *a, **k: Cancelled(), platform="win32")["cancelled"])

    def test_only_one_picker_at_a_time(self):
        with datadir._pick_lock:
            self.assertTrue(datadir.pick("folder", platform="win32", runner=lambda *a, **k: None)["busy"])

    def test_status_and_emulator_custom_flag(self):
        app, data = self.app()
        st = app.api_data_folder({})
        for key in ("folder", "logs", "is_default", "legacy_offer", "move", "can_remember"):
            self.assertIn(key, st)
        self.assertEqual(str(data / "logs"), st["logs"])
        exe = self.tmp / "duck.exe"
        exe.write_text("x")
        out = app.api_emulators({"emulator": "duckstation", "path": str(exe)})
        row = next(e for e in out["emulators"] if e["id"] == "duckstation")
        self.assertTrue(row["custom"])
        out = app.api_emulators({"emulator": "duckstation", "path": None})
        self.assertFalse(next(e for e in out["emulators"] if e["id"] == "duckstation")["custom"])

    def test_keep_remembers_the_old_folder(self):
        app, data = self.app()
        app.data_location = datadir.Resolution(data, "legacy", self.program, self.program / "LegacyPlayerData", legacy=data)
        self.assertTrue(app.api_data_folder({})["legacy_offer"])
        with mock.patch.object(datadir, "write_pointer") as wp:
            out = app.api_data_folder({"action": "keep"})
        wp.assert_called_once_with(data)
        self.assertFalse(out["legacy_offer"])

    def test_move_runs_in_the_background_stops_services_and_restarts(self):
        app, data = self.app()
        target = self.tmp / "moved"
        app.data_location = datadir.Resolution(data, "legacy", self.program, self.program / "LegacyPlayerData", legacy=data)
        with mock.patch.object(app, "_stop_for_data", return_value={"server": False, "friends": True}) as stop, \
             mock.patch.object(datadir, "move_data", return_value={"from": str(data), "to": str(target), "files": 3, "bytes": 9}) as move, \
             mock.patch.object(selfupdate, "start_detached") as start, \
             mock.patch.object(sys, "argv", ["launcher", "--data-dir", str(data), "--window"]):
            target.mkdir()
            app.api_data_folder({"action": "move", "target": str(target)})
            for _ in range(100):
                if app.quit_requested:
                    break
                time.sleep(0.05)
        self.assertTrue(app.quit_requested)
        stop.assert_called_once()
        move.assert_called_once()
        command = start.call_args.args[0]
        self.assertNotIn("--data-dir", command)                                          # the new place is remembered instead
        self.assertIn("--window", command)
        self.assertEqual({"server_share": False}, json.loads((target / "restart-after.json").read_text()))

    def test_a_failed_move_says_why_and_puts_services_back(self):
        app, data = self.app()
        with mock.patch.object(app, "_stop_for_data", return_value={"server": None, "friends": True}), \
             mock.patch.object(datadir, "move_data", side_effect=datadir.MoveError("Not enough free space there.")), \
             mock.patch.object(app, "_resume_friends_service") as resume:
            app.api_data_folder({"action": "move", "target": str(self.tmp / "else")})
            for _ in range(100):
                if app.api_data_folder({})["move"]["state"] == "problem":
                    break
                time.sleep(0.05)
        st = app.api_data_folder({})["move"]
        self.assertEqual("problem", st["state"])
        self.assertIn("free space", st["message"])
        resume.assert_called_once()
        self.assertFalse(app.quit_requested)


class Uninstall(Tmp):
    def test_logs_and_the_program_folder_parts(self):
        data = self.tmp / "data"
        (data / "logs").mkdir(parents=True)
        (data / "user_data.json").write_text("{}")
        plan = selfuninstall.plan(data)
        library = next(i for i in plan["items"] if i["key"] == "library")
        self.assertNotIn(str(data / "logs"), library["paths"])                           # listed once, as logs
        self.assertIn(str(data / "logs"), next(i for i in plan["items"] if i["key"] == "logs")["paths"])
        exe = self.program / "LegacyPlayer.exe"
        exe.write_text("x")
        (self.program / "_internal").mkdir()
        (self.program / "LegacyPlayerData").mkdir()
        lines = selfuninstall.cleanup_lines(exe, [data / "logs"], data, selfuninstall.program_extras(exe))
        joined = "\n".join(lines)
        self.assertIn("_internal", joined)
        self.assertNotIn("LegacyPlayerData", joined)                                     # kept saves stay
        self.assertLess(joined.index("goto again"), joined.index(str(data)))            # the data folder goes after the program
        self.assertTrue(lines[-1].startswith('(goto) 2>nul & del "%~f0" & rmdir "'))     # the program folder only when empty


class Packaging(unittest.TestCase):
    def test_build_is_one_folder_and_keeps_local_data(self):
        bat = text("build_exe.bat")
        self.assertIn("--onedir", bat)
        self.assertNotIn("--onefile", bat)
        self.assertIn("LegacyPlayerData", bat)                                           # moved aside and back around the build
        self.assertIn("dist\\LegacyPlayer\\LegacyPlayer.exe", bat)

    def test_package_ships_the_folder_without_local_data(self):
        pack = text("tools/package_release.ps1")
        self.assertIn("_internal", pack)
        self.assertIn("'LegacyPlayerData', 'data-location.txt'", pack)
        self.assertNotIn("%USERPROFILE%", pack)

    def test_installer_keeps_data_and_downloads_into_its_own_folder(self):
        inst = text("install.ps1")
        self.assertNotIn("$env:TEMP", inst)
        self.assertIn("_internal", inst)
        self.assertNotRegex(inst, r"Remove-Item[^\n]*\$dest\s+-Recurse")
        lp = text("lp.ps1")
        self.assertNotIn("Remove-Item $dest -Recurse", lp)
        self.assertIn("LegacyPlayerData", lp)

    def test_updater_swaps_the_internal_folder(self):
        s = selfupdate.APPLY_PS1
        self.assertIn("_internal", s)
        self.assertLess(s.index("Copy-Item -LiteralPath $newInternal"), s.index("Move-Item -LiteralPath $incoming"))
        self.assertIn("$_.Name -ne '_internal'", s)
        self.assertNotIn("LegacyPlayerData", s.split("#")[0])

    def test_workflow_smoke_checks_the_folder_and_the_user_folders(self):
        wf = text("tools/release.workflow.yml")
        self.assertEqual(wf, text(".github/workflows/release.yml"))
        self.assertIn("smoke/_internal", wf)
        self.assertIn("smoke-data/logs/app.log", wf)
        self.assertIn(".legacy-player", wf)
        self.assertIn("dist\\LegacyPlayer", wf)

    def test_docs_no_longer_send_files_to_the_user_folder(self):
        for rel in ("README.md", "PRIVACY.md", "docs/RELEASE.md", "build_exe.bat", "tools/package_release.ps1"):
            body = text(rel)
            for line in body.splitlines():
                if "%USERPROFILE%\\.legacy-player" in line or "LegacyPlayer\\app.log" in line:
                    self.assertRegex(line, r"older|0\.7\.44|Versions?", f"{rel}: {line}")

    def test_relaunch_strips_the_old_data_dir(self):
        self.assertEqual(["--window", "--games", "D:\\G"],
                         selfupdate.strip_data_dir(["--data-dir", "C:\\old", "--window", "--data-dir=C:\\x", "--games", "D:\\G"]))
        with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", "C:\\LP\\LegacyPlayer.exe"):
            cmd = selfupdate.relaunch_command(Path("C:\\LP\\LegacyPlayerData\\logs\\launcher.log"), ["--window"], pid=7)
        self.assertEqual(["--relaunch-run", "7"], cmd[1:3])
        self.assertEqual("--window", cmd[-1])
        self.assertIn("--relaunch-run", text("legacy_player_app.py"))

    def test_the_app_entry_point_can_relaunch(self):
        import subprocess
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        log = tmp / "launcher.log"
        old = subprocess.Popen([sys.executable, "-c", "pass"])
        old.wait()
        subprocess.run([sys.executable, str(ROOT / "legacy_player_app.py"), "--relaunch-run", str(old.pid), str(tmp), "--log", str(log),
                        sys.executable, "-c", "print('started again')"], cwd=ROOT, timeout=60, env={**os.environ, "LP_RELAUNCH_WAIT": "1"})
        for _ in range(100):
            if log.exists() and "started again" in log.read_text():
                break
            time.sleep(0.1)
        self.assertIn("started again", log.read_text())


if __name__ == "__main__":
    unittest.main()
