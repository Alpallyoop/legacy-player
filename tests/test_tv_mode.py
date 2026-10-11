"""TV mode (the full-screen, controller-first start screen) and the live controller panel on the Controllers page.
Opens the real app in a headless browser with a few pretend games. Skipped when Playwright is not installed."""
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

# a pretend standard gamepad: tests press its buttons by changing window.__pad
FAKE_PAD = """
window.__pad = {id: 'Test Pad (STANDARD GAMEPAD Vendor: 045e Product: 028e)', index: 0, connected: true, mapping: 'standard', timestamp: 1,
  buttons: Array.from({length: 17}, () => ({pressed: false, touched: false, value: 0})), axes: [0, 0, 0, 0]};
window.__press = (i, on) => { window.__pad.buttons[i] = {pressed: on, touched: on, value: on ? 1 : 0}; };
navigator.getGamepads = () => [window.__pad, null, null, null];
"""


class TvWindowHelperTests(unittest.TestCase):
    def test_the_window_helper_does_nothing_off_windows(self):
        from launcher import winplace
        if sys.platform != "win32":
            self.assertFalse(winplace.fullscreen_titled(winplace.APP_TITLE_MARK, True))
            self.assertFalse(winplace.fullscreen_titled(winplace.APP_TITLE_MARK, False))

    def test_settings_default_to_tv_mode_with_the_intro_and_no_sounds(self):
        from launcher.catalog import SETTINGS_SCHEMA
        self.assertEqual("tv", SETTINGS_SCHEMA["start_page"]["default"])
        self.assertIn("home", SETTINGS_SCHEMA["start_page"]["choices"])
        self.assertIs(True, SETTINGS_SCHEMA["tv_intro"]["default"])
        self.assertIs(False, SETTINGS_SCHEMA["tv_sounds"]["default"])


@unittest.skipUnless(sync_playwright, "Playwright is not installed")
class TvModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        games = base / "games" / "NES"
        games.mkdir(parents=True)
        for name in ("Alpha Quest (USA).nes", "Beta Blast (USA).nes", "Castle Climber (USA).nes"):
            (games / name).write_bytes(b"NES\x1a" + b"\0" * 64)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        keep = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "LANG", "PYTHONPATH", "LOCALAPPDATA", "APPDATA")
        env = {k: os.environ[k] for k in keep if k in os.environ}
        env["LEGACY_PLAYER_NO_BACKGROUND"] = "1"
        cls.proc = subprocess.Popen([sys.executable, "-m", "launcher", "--data-dir", str(base / "data"), "--games", str(base / "games"),
                                     "--port", str(port), "--no-browser"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        line = ""
        deadline = time.time() + 30
        while time.time() < deadline and "http://" not in line:
            line = cls.proc.stdout.readline()
        found = re.search(r"http://\S+", line)
        if not found:
            cls.proc.kill()
            raise RuntimeError("the app did not start: " + line)
        cls.port = port
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()
        cls.context = cls.browser.new_context(viewport={"width": 1280, "height": 720})
        first = cls.context.new_page()
        first.goto(found.group(0))            # the one-time link sets the session cookie for this browser context
        first.wait_for_selector("#nav button", state="attached")
        first.evaluate("async () => { await api('settings', {key: 'setup_done', value: true}); }")
        first.close()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.pw.stop()
        finally:
            cls.proc.kill()
            cls.proc.wait(5)
            cls.proc.stdout.close()
            cls.tmp.cleanup()

    # ---- helpers ----
    def open(self, start_page="tv", intro=False, pad=False):
        """A fresh window of the app with these settings saved first (as the app would have them at start-up)."""
        page = self.context.new_page()
        self.problems = []
        page.on("pageerror", lambda e: self.problems.append(str(e)))
        if pad:
            page.add_init_script(FAKE_PAD)
        page.goto(f"http://127.0.0.1:{self.port}/")
        page.wait_for_selector("#nav button", state="attached")
        page.evaluate("async ([p, i]) => { await api('settings', {key: 'start_page', value: p}); await api('settings', {key: 'tv_intro', value: i}); }", [start_page, intro])
        page.reload()
        page.wait_for_selector("#nav button", state="attached")
        self.addCleanup(page.close)
        return page

    def until(self, page, js, timeout=10.0):
        """Poll a script until it is truthy (the page's security policy forbids wait_for_function, which uses eval)."""
        end = time.time() + timeout
        while time.time() < end:
            if page.evaluate(js):
                return True
            page.wait_for_timeout(100)
        self.fail("timed out waiting for: " + js)

    def focused(self, page):
        return page.evaluate("document.activeElement && document.activeElement.dataset ? (document.activeElement.dataset.key || '') : ''")

    # ---- TV mode ----
    def test_intro_plays_and_any_key_skips_it(self):
        page = self.open(intro=True)
        page.wait_for_selector("#tvintro")
        self.assertTrue(page.evaluate("tvIntroSeek(3.5)"))
        self.assertEqual(2, page.locator("#tvintro .ti-paw").count())          # Martin's paws hang over the edge
        self.assertEqual(1, page.locator("#tvintro .ti-head svg").count())
        self.assertGreaterEqual(page.locator("#tvintro .ti-title .pxl").count(), 12)     # LEGACY PLAYER in pixel letters
        page.evaluate("tvIntroSeek(null)")
        page.keyboard.press("Space")
        self.until(page, "!document.querySelector('#tvintro')", 3)
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.assertIn("Alpha Quest", page.inner_text("#tvmode"))
        self.assertEqual([], self.problems)

    def test_rows_render_with_the_games_and_the_console_sections(self):
        page = self.open()
        page.wait_for_selector("#tvmode.in .tm-tile")
        rows = page.evaluate("[...document.querySelectorAll('#tvmode .tm-row')].map(r => r.dataset.row)")
        for want in ("continue", "favorites", "con:nes", "online", "friends", "settings", "power"):
            self.assertIn(want, rows)
        self.assertEqual(3, page.locator('#tvmode [data-row="con:nes"] .tm-tile').count())
        self.assertTrue(page.evaluate("document.documentElement.classList.contains('tm-on') && document.querySelector('#main').inert"))
        self.assertIn("Set up friends", page.inner_text('#tvmode [data-row="friends"]'))
        self.assertEqual([], self.problems)

    def test_keyboard_moves_focus_with_wrap_around(self):
        page = self.open()
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.until(page, "document.activeElement && document.activeElement.classList.contains('tm-tile')")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        self.assertEqual("g:", self.focused(page)[:2])
        first = self.focused(page)
        page.keyboard.press("ArrowRight")
        second = self.focused(page)
        self.assertNotEqual(first, second)
        page.keyboard.press("ArrowLeft")
        self.assertEqual(first, self.focused(page))
        page.keyboard.press("ArrowLeft")                      # wraps to the last game of the row
        self.assertEqual(page.evaluate("document.querySelector('[data-row=\"con:nes\"] .tm-tile:last-child').dataset.key"), self.focused(page))
        page.keyboard.press("Tab")                            # Tab: next row
        self.assertEqual("online", page.evaluate("document.activeElement.closest('.tm-row').dataset.row"))
        self.assertIn("Host a room", page.inner_text("#tm-h1") + page.inner_text("#tm-h2"))

    def test_details_sheet_opens_and_closes(self):
        page = self.open()
        page.wait_for_selector("#tvmode.in .tm-tile")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        key = self.focused(page)
        page.keyboard.press("Enter")
        page.wait_for_selector(".tm-layer .tm-details")
        text = page.inner_text(".tm-layer")
        self.assertIn("Play", text)
        self.assertIn("Add to favourites", text)
        self.assertIn("NES", text)
        page.keyboard.press("Escape")
        self.until(page, "!document.querySelector('.tm-layer')", 3)
        self.assertEqual(key, self.focused(page))
        # Y / slash: search with the on-screen keyboard
        page.keyboard.press("/")
        page.wait_for_selector(".tm-kb")
        for k in "BETA":
            page.keyboard.press(k)
        self.assertIn("BETA", page.inner_text(".tm-q"))
        self.assertEqual(1, page.locator(".tm-results .tm-tile").count())
        page.keyboard.press("Escape")
        self.until(page, "!document.querySelector('.tm-layer')", 3)

    def test_exit_asks_at_the_top_and_leaves_the_normal_window(self):
        page = self.open()
        page.wait_for_selector("#tvmode.in .tm-tile")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Escape")                          # Back first: to the first row
        self.assertEqual("continue", page.evaluate("document.activeElement.closest('.tm-row').dataset.row"))
        page.keyboard.press("Escape")                          # at the top: asks
        page.wait_for_selector(".tm-layer")
        self.assertIn("Exit TV mode?", page.inner_text(".tm-layer"))
        page.keyboard.press("Enter")
        self.until(page, "!document.querySelector('#tvmode')", 3)
        self.assertFalse(page.evaluate("document.documentElement.classList.contains('tm-on') || !!document.querySelector('#main').inert"))
        # F11 (or Games > TV mode) brings it back; nav() to any page leaves it again
        page.keyboard.press("F11")
        page.wait_for_selector("#tvmode.in .tm-tile")
        page.evaluate('nav("library")')
        self.until(page, "!document.querySelector('#tvmode')", 3)
        page.wait_for_selector("#main .game")

    def test_other_start_page_does_not_enter_tv_mode(self):
        page = self.open(start_page="home")
        page.wait_for_selector("text=Your emulators")
        page.wait_for_timeout(1200)
        self.assertEqual(0, page.locator("#tvmode, #tvintro").count())
        self.assertIn("TV mode", page.inner_text("#main"))        # Home offers it
        self.assertEqual([], self.problems)

    def test_controller_drives_tv_mode_and_back_start_opens_it(self):
        page = self.open(start_page="home", pad=True)
        page.wait_for_selector("text=Your emulators")
        page.evaluate("__press(8, true); __press(9, true)")      # hold Back + Start for a second
        page.wait_for_selector("#tvmode.in .tm-tile", timeout=6000)
        page.evaluate("__press(8, false); __press(9, false)")
        page.wait_for_timeout(300)
        self.until(page, "document.activeElement && document.activeElement.classList.contains('tm-tile')")
        before = self.focused(page)
        page.evaluate("__press(13, true)")                         # D-pad down
        page.wait_for_timeout(150)
        page.evaluate("__press(13, false)")
        self.until(page, f"(document.activeElement.dataset.key || '') !== {before!r}", 3)
        self.until(page, "document.querySelector('#tm-pad').textContent.includes('Test Pad')", 3)     # the top bar names the pad
        for _ in range(2):                                         # B: back to the first row, then it asks before leaving
            page.evaluate("__press(1, true)")
            page.wait_for_timeout(150)
            page.evaluate("__press(1, false)")
            page.wait_for_timeout(150)
        page.wait_for_selector(".tm-layer")
        self.assertIn("Exit TV mode?", page.inner_text(".tm-layer"))
        self.assertEqual([], self.problems)

    # ---- Controllers page ----
    def test_controllers_page_shows_the_live_pad_and_lights_a_pressed_button(self):
        page = self.open(start_page="home", pad=True)
        page.evaluate('nav("controllers")')
        page.wait_for_selector(".lpanel")
        self.until(page, "!document.querySelector('.lpanel').classList.contains('none')")
        self.assertIn("Test Pad", page.inner_text(".lpanel"))
        self.assertEqual(0, page.locator('.lpanel [data-s="0"].on').count())
        page.evaluate("__press(0, true); __pad.axes[0] = 0.9")
        self.until(page, "!!document.querySelector('.lpanel [data-s=\"0\"].on')", 3)
        self.until(page, "!!document.querySelector('.padmap tr.hot')", 3)          # the mapping row it controls lights up too
        self.assertTrue(page.evaluate("document.querySelector('.lpanel [data-st=\"l\"]').classList.contains('out')"))
        page.evaluate("__press(0, false)")
        self.until(page, "!document.querySelector('.lpanel [data-s=\"0\"].on')", 3)
        self.assertEqual([], self.problems)

    def test_controllers_page_without_a_pad_says_so(self):
        page = self.open(start_page="home")
        page.evaluate('nav("controllers")')
        page.wait_for_selector(".lpanel")
        self.assertIn("No controller detected", page.inner_text(".lpanel"))


if __name__ == "__main__":
    unittest.main()
