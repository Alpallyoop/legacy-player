"""The app window is a browser profile of its own: it must not sign in, sync or talk to the browser maker by itself."""
import unittest
from pathlib import Path

from launcher.shell import QUIET_BROWSER_FLAGS, app_window_command


class QuietWindow(unittest.TestCase):
    def test_no_sign_in_no_sync_no_background_traffic(self):
        cmd = app_window_command("msedge.exe", "http://127.0.0.1:1/x", Path("p"), platform="win32")
        for flag in ("--disable-sync", "--disable-background-networking", "--no-first-run", "--no-pings"):
            self.assertIn(flag, cmd)
        feats = next(f for f in cmd if f.startswith("--disable-features="))
        self.assertIn("msImplicitSignin", feats)
        self.assertEqual(1, sum(1 for f in cmd if f.startswith("--disable-features=")))   # one list: a second would replace it
        self.assertTrue(set(QUIET_BROWSER_FLAGS) <= set(cmd))


if __name__ == "__main__":
    unittest.main()
