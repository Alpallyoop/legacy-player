"""Two real Legacy Player apps in a headless browser: the host starts their server, the second player connects with the
server code, and through the Friends page (no friends link, nothing else set up) they become friends and exchange a
message, which travels through the host's game server. Skipped when Playwright is not installed."""
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:      # pragma: no cover
    sync_playwright = None

ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_app(base: Path, name: str):
    games = base / name / "games" / "NES"
    games.mkdir(parents=True)
    (games / "Alpha Quest (USA).nes").write_bytes(b"NES\x1a" + b"\0" * 64)
    keep = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "LANG", "PYTHONPATH", "LOCALAPPDATA", "APPDATA")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["LEGACY_PLAYER_NO_BACKGROUND"] = "1"
    proc = subprocess.Popen([sys.executable, "-m", "launcher", "--data-dir", str(base / name / "data"), "--games", str(base / name / "games"),
                             "--port", str(free_port()), "--no-browser"], cwd=ROOT, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    line, deadline = "", time.time() + 30
    while time.time() < deadline and "http://" not in line:
        line = proc.stdout.readline()
    found = re.search(r"http://\S+", line)
    if not found:
        proc.kill()
        raise RuntimeError("the app did not start: " + line)
    return proc, found.group(0)


@unittest.skipUnless(sync_playwright, "Playwright is not installed")
class TwoAppsBecomeFriendsThroughTheHostsServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.host_proc, self.host_url = start_app(base, "al")
        self.guest_proc, self.guest_url = start_app(base, "bro")

    def tearDown(self):
        for proc in (self.host_proc, self.guest_proc):
            proc.kill()
            proc.wait(5)
        self.tmp.cleanup()

    def test_friends_and_a_message_over_the_server_code(self):
        def api(page, name, body=None):
            return page.evaluate("([n,b])=>api(n,b)", [name, body or {}])

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                host = browser.new_page(viewport={"width": 1280, "height": 860})
                guest = browser.new_page(viewport={"width": 1280, "height": 860})
                for page, url in ((host, self.host_url), (guest, self.guest_url)):
                    page.goto(url)
                    page.wait_for_selector("#nav button")
                api(host, "settings", {"key": "display_name", "value": "Al"})
                api(guest, "settings", {"key": "display_name", "value": "Bro"})
                # the host starts their server for friends (no router changes in a test) and shares the code
                api(host, "settings", {"key": "server_auto_open", "value": False})
                api(host, "settings", {"key": "server_port", "value": free_port()})
                started = api(host, "server_control", {"action": "start", "share": True})
                self.assertTrue(started["running"], started)
                try:
                    code = api(host, "server_code", {"address": "127.0.0.2"})["code"]      # "another computer" on loopback
                    joined = api(guest, "server_connect", {"code": code})
                    self.assertTrue(joined["connected"], joined)
                    # both open Friends: no link was ever set, the page offers the server's friends list
                    for page in (host, guest):
                        page.evaluate("nav('friends')")
                        page.get_by_role("button", name="Get my friend code").click()
                        page.wait_for_selector(".code.mid")
                    self.assertIn("your own server", host.inner_text("#main"))
                    self.assertIn("the server you joined with a server code", guest.inner_text("#main"))
                    host_code = host.inner_text(".code.mid").strip()
                    guest.fill("input[aria-label=\"Friend's code\"]", host_code)
                    guest.get_by_role("button", name="Add friend").click()
                    guest.wait_for_timeout(500)
                    host.evaluate("S.friendTab='incoming';go()")
                    host.get_by_role("button", name="Accept").click()
                    host.wait_for_timeout(500)
                    host.evaluate("S.friendTab='friends';go()")
                    host.get_by_role("button", name="Message").first.click()
                    host.wait_for_selector("text=Say hi!")                       # the conversation has loaded (no redraw under the typing)
                    host.wait_for_timeout(300)
                    host.fill("input[aria-label=Message]", "hi brother, see you in the castle")
                    host.get_by_role("button", name="Send").click()
                    host.wait_for_selector("text=hi brother, see you in the castle")
                    guest.evaluate("S.friendTab='inbox';S.friendSel=null;go()")
                    guest.wait_for_selector("text=hi brother, see you in the castle", timeout=15000)
                    guest.screenshot(path=str(Path(self.tmp.name) / "guest_friends.png"))
                finally:
                    api(host, "server_control", {"action": "stop"})
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
