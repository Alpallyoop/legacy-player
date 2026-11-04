"""Uninstall never deletes a logs folder the player picked: only Legacy Player's own log files in it (audit 2026-11-04)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from launcher import datadir, selfuninstall


class PickedLogsFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.data = base / "LegacyPlayerData"
        self.data.mkdir()
        (self.data / "user_data.json").write_text("{}")
        self.mine = base / "Documents"
        self.mine.mkdir()
        (self.mine / "thesis.docx").write_text("precious")
        datadir.set_logs_folder(self.data, self.mine)
        (self.mine / "app.log").write_text("log line\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_own_log_files_are_removed(self):
        captured = {}
        with mock.patch.object(selfuninstall, "_spawn_cleanup", lambda exe, others, purge, extras=(): captured.update(others=others)):
            selfuninstall.execute(self.data, keep_saves=True, remove_program=False)
        targets = [Path(p) for p in captured["others"]]
        self.assertNotIn(self.mine, targets)
        self.assertIn(self.mine / "app.log", targets)
        script = "\n".join(selfuninstall.cleanup_lines(None, captured["others"], None))
        self.assertNotIn(f'rmdir /s /q "{self.mine}"', script)
        self.assertIn(f'del /f /q "{self.mine / "app.log"}"', script)

    def test_the_default_logs_folder_still_goes_whole(self):
        datadir.set_logs_folder(self.data, None)
        (self.data / "logs").mkdir(exist_ok=True)
        self.assertEqual([self.data / "logs"], selfuninstall.log_paths(self.data, self.data / "logs"))


if __name__ == "__main__":
    unittest.main()
