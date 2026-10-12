"""The in-app uninstaller also removes the Start menu shortcut install.ps1 made (only when it removes the program)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher import selfuninstall


class ShortcutGoesWithTheProgram(unittest.TestCase):
    def run_it(self, remove_program: bool):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data = base / "LegacyPlayerData"
            data.mkdir()
            exe = base / "prog" / "LegacyPlayer.exe"
            exe.parent.mkdir()
            exe.write_text("x")
            lnk = base / "Legacy Player.lnk"
            lnk.write_text("shortcut")
            with mock.patch.object(selfuninstall, "check_data_dir", return_value=None), \
                    mock.patch.object(selfuninstall, "program_file", return_value=exe), \
                    mock.patch.object(selfuninstall, "start_menu_shortcut", return_value=lnk), \
                    mock.patch.object(selfuninstall, "_spawn_cleanup"):
                out = selfuninstall.execute(data, keep_saves=True, remove_program=remove_program)
            return out, lnk.exists()

    def test_removed_with_the_program(self):
        out, still_there = self.run_it(True)
        self.assertFalse(still_there)
        self.assertIn("shortcut", [s["key"] for s in out["steps"]])

    def test_kept_when_the_program_stays(self):
        out, still_there = self.run_it(False)
        self.assertTrue(still_there)
        self.assertNotIn("shortcut", [s["key"] for s in out["steps"]])

    def test_no_shortcut_off_windows(self):
        with mock.patch.object(selfuninstall.os, "name", "posix"):
            self.assertIsNone(selfuninstall.start_menu_shortcut())


if __name__ == "__main__":
    unittest.main()
