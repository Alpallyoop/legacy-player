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

# a pretend standard gamepad: tests press its buttons by changing window.__pad. window.__pads is what the browser
# reports (more pads can be plugged in with __plug); __press(i, on, n) presses button i on pad n (default the first).
FAKE_PAD = """
window.__mkpad = (index, id, mapping, nb, axes) => ({id, index, connected: true, mapping, timestamp: 1,
  buttons: Array.from({length: nb}, () => ({pressed: false, touched: false, value: 0})), axes: axes.slice()});
window.__pad = __mkpad(0, 'Test Pad (STANDARD GAMEPAD Vendor: 045e Product: 028e)', 'standard', 17, [0, 0, 0, 0]);
window.__pads = [window.__pad, null, null, null];
window.__plug = (index, pad) => { pad.index = index; window.__pads[index] = pad; return pad; };
window.__press = (i, on, n) => { const p = window.__pads[n || 0]; p.buttons[i] = {pressed: on, touched: on, value: on ? 1 : 0}; };
navigator.getGamepads = () => window.__pads.slice();
"""

# one press and let go that lasts a single controller read (padPoll runs every 16 ms): the shortest tap a player can make
TAP = """async ([b, n]) => {
  const poll = async () => { const k = PADHUB.polls; while (PADHUB.polls === k) await new Promise(r => setTimeout(r, 1)); };
  __press(b, true, n); await poll(); __press(b, false, n); await poll(); }"""

# Every tile in TV mode must do something: open a sheet or a dialog, move focus, change a setting, or open a page.
# The calls that would leave TV mode, quit, download or start servers are recorded instead of run.
NO_DEAD_TILES = """async () => {
  const calls = [];
  for (const n of ['quitApp', 'updateEverything', 'exitTvMode', 'tvOpenPage', 'tvFullscreen', 'pickTheme', 'tvSave', 'tvStartServer',
                   'tvLoadRooms', 'tvFriends', 'tvReload', 'launchGame']) {
    window[n] = (...a) => { calls.push(n); return Promise.resolve(false); };
  }
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const dead = [], seen = [];
  const rows = TVM.rows.map(r => ({id: r.id, tiles: r.tiles.slice()}));
  for (const r of rows) {
    const keys = r.tiles.map(t => t.key);
    if (new Set(keys).size !== keys.length) dead.push(r.id + ': two tiles with the same key');
    for (const t of r.tiles) {
      seen.push(r.id + '/' + t.label);
      if (typeof t.act !== 'function') { dead.push(r.id + '/' + t.label + ': no action'); continue; }
      const before = {layers: TVM.layers.length, calls: calls.length, r: TVM.r, toasts: document.querySelectorAll('#toasts .toast').length};
      try { await Promise.race([Promise.resolve(t.act()), sleep(500)]); } catch (e) { dead.push(r.id + '/' + t.label + ': ' + e.message); }   // a sheet waiting for an answer stays open
      await sleep(150);
      const did = TVM.layers.length > before.layers || calls.length > before.calls || TVM.r !== before.r ||
        !!document.querySelector('.modal') || document.querySelectorAll('#toasts .toast').length > before.toasts;
      if (!did) dead.push(r.id + '/' + t.label + ': nothing happened');
      document.querySelectorAll('.modal').forEach(m => m.remove());
      tvCloseAll();
    }
  }
  return {dead, seen};
}"""


class TvWindowHelperTests(unittest.TestCase):
    def test_the_window_helper_does_nothing_off_windows(self):
        from launcher import winplace
        if sys.platform != "win32":
            self.assertFalse(winplace.fullscreen_titled(winplace.APP_TITLE_MARK, True))
            self.assertFalse(winplace.fullscreen_titled(winplace.APP_TITLE_MARK, False))

    def test_the_app_window_opens_full_screen_for_tv_mode_off_windows(self):
        from launcher.shell import app_window_command, opens_in_tv_mode
        on = app_window_command("chrome", "http://x/", Path("/p"), fullscreen=True, platform="linux")
        self.assertIn("--start-fullscreen", on)
        self.assertIn("--app=http://x/", on)
        self.assertNotIn("--start-fullscreen", app_window_command("chrome", "http://x/", Path("/p"), fullscreen=False, platform="linux"))
        # Windows keeps its own window placement (launcher/winplace.py), which TV mode can undo when it is left
        self.assertNotIn("--start-fullscreen", app_window_command("msedge.exe", "http://x/", Path("/p"), fullscreen=True, platform="win32"))
        self.assertTrue(opens_in_tv_mode({"setup_done": True, "start_page": "tv"}))
        self.assertTrue(opens_in_tv_mode({"setup_done": True, "start_page": "last", "last_page": "tv"}))
        self.assertTrue(opens_in_tv_mode({"setup_done": True, "start_page": "console"}))
        self.assertFalse(opens_in_tv_mode({"setup_done": True, "start_page": "home"}))
        self.assertFalse(opens_in_tv_mode({"setup_done": True, "start_page": "last", "last_page": "library"}))
        self.assertFalse(opens_in_tv_mode({"setup_done": False, "start_page": "tv"}))      # the first start shows the welcome steps

    def test_console_mode_settings_become_tv_mode(self):
        import json
        from launcher.catalog import Catalog, SETTINGS_SCHEMA
        self.assertNotIn("console", SETTINGS_SCHEMA["start_page"]["choices"])
        self.assertIn("tv", SETTINGS_SCHEMA["last_page"]["choices"])
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "user_data.json").write_text(json.dumps({"settings": {"start_page": "console", "last_page": "console"}}), encoding="utf-8")
            cat = Catalog(Path(tmp))
            self.assertEqual("tv", cat.settings()["start_page"])
            self.assertEqual("tv", cat.settings()["last_page"])
            cat.set_setting("start_page", "console")             # an old page or script asking for Console mode gets TV mode
            self.assertEqual("tv", cat.settings()["start_page"])
            cat.set_setting("last_page", "tv")
            self.assertEqual("tv", cat.settings()["last_page"])

    def test_settings_default_to_tv_mode_with_the_intro_and_no_sounds(self):
        from launcher.catalog import SETTINGS_SCHEMA
        self.assertEqual("tv", SETTINGS_SCHEMA["start_page"]["default"])
        self.assertIn("home", SETTINGS_SCHEMA["start_page"]["choices"])
        self.assertIs(True, SETTINGS_SCHEMA["tv_intro"]["default"])
        self.assertIs(False, SETTINGS_SCHEMA["tv_sounds"]["default"])


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(sync_playwright, "Playwright is not installed")
class _TvApp(unittest.TestCase):
    """The real app on a pretend library, opened in a headless browser. Subclasses set LIBRARY {folder: [file names]}
    and may preseed user_data.json (prepare) or set things up through the API (configure)."""
    LIBRARY = {"NES": ["Alpha Quest (USA).nes", "Beta Blast (USA).nes", "Castle Climber (USA).nes"]}

    @classmethod
    def prepare(cls, base: Path) -> None:
        pass

    @classmethod
    def configure(cls, page) -> None:
        pass

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        (base / "games").mkdir()
        for folder, names in cls.LIBRARY.items():
            (base / "games" / folder).mkdir()
            for name in names:
                (base / "games" / folder / name).write_bytes(b"NES\x1a" + b"\0" * 64)
        cls.base = base
        cls.prepare(base)
        port = _free_port()
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
        cls.configure(first)
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
    def open(self, start_page="tv", intro=False, pad=False, width=1280, height=720, before=None):
        """A fresh window of the app with these settings saved first (as the app would have them at start-up).
        before(page) runs before the page loads (to fake API answers with page.route)."""
        page = self.context.new_page()
        page.set_viewport_size({"width": width, "height": height})
        self.problems = []
        page.on("pageerror", lambda e: self.problems.append(str(e)))
        if pad:
            page.add_init_script(FAKE_PAD)
        if before:
            before(page)
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

    def rows(self, page):
        return page.evaluate("[...document.querySelectorAll('#tvmode .tm-row')].map(r => r.dataset.row)")

    def go_row(self, page, row):
        """Focus the first tile of a row with the keyboard (Tab: next row)."""
        for _ in range(40):
            if page.evaluate("(document.activeElement.closest && document.activeElement.closest('.tm-row') || {dataset: {}}).dataset.row") == row:
                return
            page.keyboard.press("Tab")
        self.fail("no row " + row)

    def tap(self, page, button, pad=0):
        """Press and let go of one button on the pretend pad (0 A, 1 B, 2 X, 3 Y, 4 LB, 5 RB, 12-15 D-pad), held for a
        single controller read: the shortest tap there is."""
        page.evaluate(TAP, [button, pad])
        page.wait_for_timeout(30)

    def focus_tile(self, page, row, key):
        """Focus a tile by its key with the keyboard (Tab to the row, then right until it is focused)."""
        self.go_row(page, row)
        for _ in range(60):
            if self.focused(page) == key:
                return
            page.keyboard.press("ArrowRight")
        self.fail("no tile " + key + " in " + row)

    def check_no_dead_tiles(self, page):
        out = page.evaluate(NO_DEAD_TILES)
        self.assertEqual([], out["dead"])
        self.assertGreater(len(out["seen"]), 10)
        return out["seen"]

    def check_fits(self, page, width, height):
        """The hints bar is on screen, the hero is not empty and 1.5 to 2.5 rows show below it."""
        page.set_viewport_size({"width": width, "height": height})
        page.wait_for_timeout(300)
        box = page.evaluate("""() => { const r = s => document.querySelector(s).getBoundingClientRect();
          const row = document.querySelector('#tvmode .tm-row.cur') || document.querySelector('#tvmode .tm-row');
          return {hints: r('#tm-hints').bottom, rows: r('#tvmode .tm-rows').height, row: row.getBoundingClientRect().height,
                  h1: document.querySelector('#tm-h1').textContent, hero: r('#tm-hero').height}; }""")
        self.assertLessEqual(box["hints"], height + 1, (width, height))
        self.assertTrue(box["h1"].strip())
        self.assertGreater(box["hero"], 80)
        self.assertTrue(1.4 <= box["rows"] / box["row"] <= 2.6, (width, height, box))


class TvModeTests(_TvApp):
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
        rows = self.rows(page)
        # nothing played and no favourites: "Jump in" and "Recently added" (with a Pick favourites tile) instead of empty rows
        for want in ("jumpin", "recent", "ready", "con:nes", "online", "friends", "tools", "settings", "power"):
            self.assertIn(want, rows)
        self.assertNotIn("continue", rows)
        self.assertNotIn("favorites", rows)
        self.assertIn("Pick favourites", page.inner_text('#tvmode [data-row="recent"]'))
        self.assertEqual(3, page.locator('#tvmode [data-row="con:nes"] .tm-tile[data-key^="g:"]').count())
        # no emulator: said in place, with what to do about it
        self.assertIn("needs an emulator", page.inner_text('#tvmode [data-row="con:nes"] .tm-rt'))
        self.assertIn("Get an emulator for NES", page.inner_text('#tvmode [data-row="con:nes"]'))
        self.assertIn("Get emulators", page.inner_text('#tvmode [data-row="ready"]'))
        # games without covers get a made-up box: console, a pixel badge, the title
        ph = page.locator('#tvmode [data-row="con:nes"] .tm-ph').first
        self.assertIn("Alpha Quest", ph.inner_text())
        self.assertEqual(1, ph.locator("svg.ph-sp").count())
        self.assertTrue(page.evaluate("document.documentElement.classList.contains('tm-on') && document.querySelector('#main').inert"))
        # friends use the game server's friends list by default, so the tile asks to finish setting up (get a friend code)
        self.assertRegex(page.inner_text('#tvmode [data-row="friends"]'), "Set up friends|Finish setting up friends")
        self.assertEqual([], self.problems)

    def test_keyboard_moves_focus_with_wrap_around(self):
        page = self.open()
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.until(page, "document.activeElement && document.activeElement.classList.contains('tm-tile')")
        self.go_row(page, "con:nes")
        self.assertEqual("g:", self.focused(page)[:2])
        first = self.focused(page)
        page.keyboard.press("ArrowRight")
        second = self.focused(page)
        self.assertNotEqual(first, second)
        page.keyboard.press("ArrowLeft")
        self.assertEqual(first, self.focused(page))
        page.keyboard.press("ArrowLeft")                      # wraps to the last tile of the row
        self.assertEqual(page.evaluate("document.querySelector('[data-row=\"con:nes\"] .tm-tile:last-child').dataset.key"), self.focused(page))
        page.keyboard.press("Tab")                            # Tab: next row
        self.assertEqual("online", page.evaluate("document.activeElement.closest('.tm-row').dataset.row"))
        self.assertIn("Server", page.inner_text("#tm-h1"))
        self.assertIn("Start my server", page.inner_text('#tvmode [data-row="online"]'))

    def test_details_sheet_opens_and_closes(self):
        page = self.open()
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.until(page, "document.activeElement && document.activeElement.classList.contains('tm-tile')")
        self.go_row(page, "con:nes")
        key = self.focused(page)
        self.assertIn(page.inner_text("#tm-h1"), ("Alpha Quest", "Beta Blast", "Castle Climber"))     # the hero shows the game
        page.keyboard.press("Enter")
        page.wait_for_selector(".tm-layer .tm-details")
        text = page.inner_text(".tm-layer")
        self.assertIn("Play", text)
        self.assertIn("Add to favourites", text)
        self.assertIn("NES", text)
        self.assertIn("No emulator for NES", text)          # why Play is missing, and the way out
        self.assertIn("Get an emulator for NES", text)
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
        self.assertEqual("jumpin", page.evaluate("document.activeElement.closest('.tm-row').dataset.row"))
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
        self.tap(page, 13)                                         # D-pad down
        self.until(page, f"(document.activeElement.dataset.key || '') !== {before!r}", 3)
        self.until(page, "document.querySelector('#tm-pad').textContent.includes('Test Pad')", 3)     # the top bar names the pad
        for _ in range(2):                                         # B: back to the first row, then it asks before leaving
            self.tap(page, 1)
        page.wait_for_selector(".tm-layer")
        self.assertIn("Exit TV mode?", page.inner_text(".tm-layer"))
        self.assertEqual([], self.problems)

    def test_no_dead_tiles_and_disabled_buttons_say_why(self):
        page = self.open()
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.until(page, "document.activeElement && document.activeElement.classList.contains('tm-tile')")
        self.go_row(page, "con:nes")
        page.keyboard.press("Enter")
        page.wait_for_selector(".tm-layer .tm-details")
        why = page.evaluate("[...document.querySelectorAll('.tm-layer .tm-btn:disabled')].map(b => (b.querySelector('small') || {}).textContent || b.title || '')")
        self.assertTrue(why)
        self.assertTrue(all(w.strip() for w in why), why)
        page.keyboard.press("Escape")
        seen = self.check_no_dead_tiles(page)
        self.assertTrue(any(x.startswith("tools/") for x in seen))
        self.assertEqual([], self.problems)

    def test_a_page_opened_from_tv_mode_has_a_way_back(self):
        page = self.open()
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.until(page, "document.activeElement && document.activeElement.classList.contains('tm-tile')")
        self.go_row(page, "settings")
        page.keyboard.press("End")                              # All settings
        key = self.focused(page)
        page.keyboard.press("Enter")
        self.until(page, "!document.querySelector('#tvmode') && S.tab === 'settings'", 3)
        page.click("#tvback .btn.primary")
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.until(page, f"(document.activeElement.dataset || {{}}).key === {key!r}", 5)      # back on the same tile
        self.assertEqual(0, page.locator("#tvback").count())

    def test_layout_fits_common_screens(self):
        page = self.open()
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.until(page, "document.activeElement && document.activeElement.classList.contains('tm-tile')")
        for w, h in ((1920, 1080), (1280, 720), (1280, 800), (1024, 768)):
            self.check_fits(page, w, h)

    def test_doctor_check_up_opens_in_tv_mode(self):
        page = self.open()
        page.wait_for_selector("#tvmode.in .tm-tile")
        page.evaluate("tvDoctor()")
        self.until(page, "!!document.querySelector('.tm-layer') && /games? ·/.test(document.querySelector('.tm-layer').innerText)", 8)
        # the NES games need an emulator; with RetroArch on this computer (say /usr/bin/retroarch) the doctor rightly
        # says it is here but has no NES core yet
        text = page.inner_text(".tm-layer")
        self.assertTrue("still need" in text or "has no NES core" in text, text)

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


class TvEmptyLibraryTests(_TvApp):
    """No games yet: Martin's welcome with steps that work from the sofa."""
    LIBRARY = {}

    def test_welcome_hero_rows_and_adding_a_folder_with_the_on_screen_keyboard(self):
        page = self.open(width=1280, height=800)
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.until(page, "document.activeElement && document.activeElement.classList.contains('tm-tile')")
        hero = page.inner_text("#tm-hero")
        for want in ("Add your games folder", "Get emulators", "Scan this computer"):
            self.assertIn(want, hero)
        self.assertEqual(1, page.locator("#tm-hero .tm-hart.martin svg").count())
        self.assertEqual(["start", "online", "friends", "tools", "settings", "power"], self.rows(page))
        self.assertIn("Selected", page.inner_text("#tm-h2"))
        self.check_fits(page, 1280, 800)
        self.check_no_dead_tiles(page)
        # Add your games folder > Type the folder path > on-screen keyboard
        more = self.base / "more" / "SNES"
        more.mkdir(parents=True)
        for name in ("Gamma Racer (USA).sfc", "Delta Force Ten (Europe).sfc"):
            (more / name).write_bytes(b"\0" * 512)
        page = self.open(width=1280, height=800)              # a fresh window: the dead-tile check replaced some functions
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.until(page, "document.activeElement && document.activeElement.dataset.key === 'i:step1'")
        page.keyboard.press("Enter")
        page.wait_for_selector(".tm-layer >> text=Type the folder path")
        page.click(".tm-layer >> text=Type the folder path")
        page.wait_for_selector(".tm-kb")
        page.keyboard.type(str(self.base / "more"))
        self.assertIn("more", page.inner_text(".tm-q"))
        page.click(".tm-key.primary")
        self.until(page, "TVM.rows.some(r => r.id === 'con:snes')", 15)
        self.until(page, "!document.querySelector('.tm-layer')", 5)
        self.assertIn("jumpin", self.rows(page))
        self.assertEqual([], self.problems)


class TvRealisticLibraryTests(_TvApp):
    """A library like a real one: several consoles, favourites, something played, an emulator for one console."""
    LIBRARY = {
        "NES": ["Super Mario Bros. 3 (USA).nes", "Contra (USA).nes", "The Legend of Zelda (USA).nes", "Mega Man 2 (USA).nes"],
        "SNES": ["Super Mario World (USA).sfc", "Super Mario Kart (USA).sfc", "Chrono Trigger (USA).sfc", "Street Fighter II Turbo (USA).sfc"],
        "N64": ["Mario Kart 64 (Europe).z64", "GoldenEye 007 (USA).z64", "Super Mario 64 (USA).z64"],
        "GB": ["Tetris (World).gb", "Kirby's Dream Land (USA, Europe).gb"],
    }

    @classmethod
    def prepare(cls, base):
        import hashlib
        import json
        gid = hashlib.sha1("games/SNES/Super Mario World (USA).sfc".encode()).hexdigest()[:16]
        (base / "data").mkdir()
        (base / "data" / "user_data.json").write_text(json.dumps({"history": {gid: {"plays": 3, "last_played": time.time() - 3600}}}), encoding="utf-8")

    @classmethod
    def configure(cls, page):
        fake = cls.base / "emu" / "mesen.exe"
        fake.parent.mkdir()
        fake.write_bytes(b"MZ")
        page.evaluate("""async (f) => { await api('emulators', {emulator: 'mesen', path: f});
          const lib = await api('library', {sort: 'title'});
          for (const t of ['Chrono Trigger', 'Tetris']) await api('favorite', {id: lib.games.find(g => g.title === t).id, favorite: true}); }""", str(fake))

    def test_rows_hero_and_placeholders(self):
        page = self.open(width=1920, height=1080)
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.until(page, "document.activeElement && document.activeElement.classList.contains('tm-tile')")
        rows = self.rows(page)
        for want in ("continue", "favorites", "recent", "ready", "multi", "con:nes", "con:snes", "con:n64", "con:gb", "online", "friends", "tools", "settings", "power"):
            self.assertIn(want, rows)
        self.assertEqual("continue", rows[0])
        self.assertEqual("Super Mario World", page.inner_text("#tm-h1"))         # the hero: the game you played last
        self.assertIn("SNES", page.inner_text("#tm-hero .tm-facts"))
        self.assertIn("Played 3 times", page.inner_text("#tm-h2"))
        self.assertEqual(2, page.locator('[data-row="favorites"] .tm-tile[data-key^="g:"]').count())
        self.assertEqual(4, page.locator('[data-row="ready"] .tm-tile').count())     # only the NES games have an emulator
        self.assertIn("ready", page.inner_text('[data-row="con:nes"] .tm-rt'))
        self.assertIn("needs an emulator", page.inner_text('[data-row="con:snes"] .tm-rt'))
        multi = page.inner_text('[data-row="multi"]')
        self.assertIn("Super Mario Kart", multi)
        self.assertNotIn("The Legend of Zelda", multi)                              # a one-player game
        self.assertIn("4P", page.locator('[data-row="multi"] .tm-tile[data-key^="g:"]').first.inner_text())
        # a game with an emulator: Play is in the hero; P plays it
        self.go_row(page, "con:nes")
        self.assertIn("Play", page.inner_text("#tm-hero .tm-acts"))
        self.assertIn("Opens in", page.inner_text("#tm-h2"))
        page.evaluate("() => { window.__launched = []; window.launchGame = (g) => { __launched.push(g.title); return Promise.resolve(null); }; }")
        page.keyboard.press("p")
        self.until(page, "__launched.length === 1", 3)
        self.assertEqual(self.focused(page), "g:" + page.evaluate("TVM.lib.games.find(g => g.title === __launched[0]).id"))
        for w, h in ((1920, 1080), (1280, 720), (1024, 768)):
            self.check_fits(page, w, h)
        self.assertEqual([], self.problems)

    def test_no_dead_tiles_with_a_full_library(self):
        page = self.open()
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.until(page, "document.activeElement && document.activeElement.classList.contains('tm-tile')")
        seen = self.check_no_dead_tiles(page)
        self.assertTrue(any(x.startswith("favorites/") for x in seen))
        self.assertEqual([], self.problems)


def _fake(page, calls, name, answer):
    """Answer /api/<name> with answer(body) -> dict (or a fixed dict), and keep each request body in calls[name]."""
    import json

    def handle(route):
        try:
            body = route.request.post_data_json or {}
        except Exception:      # pragma: no cover
            body = {}
        calls.setdefault(name, []).append(body)
        out = answer(body) if callable(answer) else answer
        route.fulfill(status=200, content_type="application/json", body=json.dumps(out))
    page.route("**/api/" + name, handle)


class TvControllerTests(_TvApp):
    """TV mode driven by the pretend pad: one press is one press, the TV sheets for emulators, friends, a friend's
    server and the room, Console mode merged into TV mode, and pages opened from TV mode."""

    def ready(self, page):
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.until(page, "document.activeElement && document.activeElement.classList.contains('tm-tile')")

    # ---- 1. a held press is one press ----
    def test_one_held_press_on_quit_asks_and_does_not_quit(self):
        calls = {}
        page = self.open(pad=True, before=lambda p: _fake(p, calls, "quit", {}))
        self.ready(page)
        self.go_row(page, "power")
        page.keyboard.press("End")
        self.assertEqual("i:Quit Legacy Player", self.focused(page))
        page.evaluate("__press(0, true)")                 # A held down for longer than the dialogs' controller loop ticks
        page.wait_for_timeout(700)
        page.evaluate("__press(0, false)")
        page.wait_for_timeout(400)
        self.assertEqual(1, page.locator(".modal").count())
        self.assertIn("Quit Legacy Player?", page.inner_text(".modal"))
        self.assertNotIn("quit", calls)
        self.tap(page, 1)                                  # B: Cancel
        self.until(page, "!document.querySelector('.modal')", 3)
        self.assertNotIn("quit", calls)
        self.assertTrue(page.evaluate("TVM.on"))
        self.assertEqual([], self.problems)

    def test_more_about_this_game_stays_open_after_one_press(self):
        page = self.open(pad=True)
        self.ready(page)
        self.go_row(page, "con:nes")
        self.tap(page, 0)
        page.wait_for_selector(".tm-layer .tm-details")
        page.evaluate("[...document.querySelectorAll('.tm-layer .tm-btn')].find(b => b.textContent.includes('More about')).focus()")
        page.evaluate("__press(0, true)")
        page.wait_for_timeout(700)
        page.evaluate("__press(0, false)")
        page.wait_for_selector(".modal.gcmodal")
        page.wait_for_timeout(500)
        self.assertEqual(1, page.locator(".modal.gcmodal").count())
        self.tap(page, 1)                                  # B closes the card, and only the card
        self.until(page, "!document.querySelector('.modal')", 3)
        self.assertEqual(1, page.locator(".tm-layer .tm-details").count())

    # ---- 3a. getting emulators ----
    def test_get_emulators_asks_for_downloads_then_installs(self):
        calls, state = {}, {"done": False}
        doctor = {"issues": [{"key": "nes", "kind": "emulator", "text": "3 NES games still need an emulator (Mesen, FCEUX).", "dismissed": False}],
                  "mood": "sad", "games": 3, "emulators": [], "consoles_ready": 0, "consoles_total": 18}

        def engines(body):
            job = {"state": "done", "step": "Mesen is ready", "log": ["Mesen is ready"]} if state["done"] else {"state": "idle", "log": []}
            return {"engines": [{"id": "mesen", "name": "Mesen", "consoles": ["nes", "snes"], "can_download": True, "path": None,
                                 "official": {"kind": "github", "repo": "SourMesen/Mesen2"}},
                                {"id": "fceux", "name": "FCEUX", "consoles": ["nes"], "can_download": True, "path": None,
                                 "official": {"kind": "github", "repo": "TASEmulators/fceux"}}],
                    "allow_internet": False, "install_folder": "/data/emulators", "job": job}

        def install(body):
            state["done"] = True
            return {"job": {"state": "running", "step": "Downloading Mesen", "log": ["Downloading Mesen"]}}

        def before(p):
            _fake(p, calls, "doctor", doctor)
            _fake(p, calls, "engines", engines)
            _fake(p, calls, "engines_install", install)
        page = self.open(pad=True, before=before)
        self.ready(page)
        page.evaluate("async () => { await api('settings', {key: 'allow_internet', value: false}); S.settings.allow_internet = false; }")
        self.focus_tile(page, "con:nes", "i:emu:nes")      # "Get an emulator for NES" at the end of the NES row
        self.tap(page, 0)
        page.wait_for_selector(".tm-layer >> text=Get Mesen")
        text = page.inner_text(".tm-layer")
        self.assertIn("NES", text)
        self.assertIn("still need an emulator", text)
        self.assertIn("Internet downloads are off", text)
        self.assertEqual("Get Mesen", page.evaluate("document.activeElement.firstChild.textContent"))
        self.tap(page, 0)                                  # A: Get Mesen > first the question about downloads
        page.wait_for_selector(".tm-layer >> text=Allow")
        self.assertIn("Allow:", page.inner_text(".tm-layer:last-child"))
        self.assertNotIn("engines_install", calls)
        self.tap(page, 0)                                  # Allow
        page.wait_for_selector(".tm-layer >> text=Download Mesen?")
        self.assertIn("github.com/SourMesen/Mesen2", page.inner_text(".tm-layer:last-child"))
        self.tap(page, 0)                                  # Download
        self.until(page, "!!document.querySelector('.tm-job')", 5)
        self.assertEqual([{"engine": "mesen", "confirm": True}], calls["engines_install"])
        self.assertTrue(page.evaluate("async () => (await api('settings')).values.allow_internet"))   # the player's yes, saved
        self.until(page, "document.querySelector('.tm-job').innerText.includes('Done')", 6)
        self.tap(page, 1)                                  # B closes the sheet
        self.until(page, "!document.querySelector('.tm-layer')", 3)
        self.assertEqual([], self.problems)

    def test_get_emulators_saying_no_downloads_nothing(self):
        calls = {}

        def before(p):
            _fake(p, calls, "doctor", {"issues": [{"key": "nes", "kind": "emulator", "text": "3 NES games still need an emulator.", "dismissed": False}]})
            _fake(p, calls, "engines", {"engines": [{"id": "mesen", "name": "Mesen", "consoles": ["nes"], "can_download": True, "path": None,
                                                     "official": {"kind": "github", "repo": "SourMesen/Mesen2"}}],
                                        "allow_internet": False, "install_folder": "/data/emulators", "job": {"state": "idle", "log": []}})
            _fake(p, calls, "engines_install", {"job": {"state": "running", "log": []}})
        page = self.open(pad=True, before=before)
        self.ready(page)
        page.evaluate("async () => { await api('settings', {key: 'allow_internet', value: false}); }")
        page.evaluate("tvGetEmulators('nes')")
        page.wait_for_selector(".tm-layer >> text=Get Mesen")
        self.until(page, "(document.activeElement.textContent || '').includes('Get Mesen')", 3)
        self.tap(page, 0)
        page.wait_for_selector(".tm-layer >> text=Not now")
        self.tap(page, 1)                                  # B: not now
        page.wait_for_timeout(400)
        self.assertNotIn("engines_install", calls)
        self.assertFalse(page.evaluate("async () => (await api('settings')).values.allow_internet"))

    # ---- 3b. friends ----
    def test_friends_requests_and_messages_from_the_pad(self):
        import time as _t
        calls = {}
        now = _t.time()
        sam = {"id": "p3", "name": "Sam", "online": True, "e2e": True}
        inbox = {"me": {"id": "me1", "code": "ABCD-EFGH-JKMN", "name": "Al"}, "requests": [{"id": "p2", "name": "Bro"}], "invites": [],
                 "friends": [sam], "conversations": [{"id": "p3", "name": "Sam", "last": "hello there", "at": now - 60, "unread": 1, "online": True}],
                 "groups": [{"id": "g1", "name": "Squad", "members": [{"id": "me1", "name": "Al"}, {"id": "p3", "name": "Sam"}], "last": "gg", "last_name": "Sam",
                             "at": now - 120, "unread": 0, "owner": "p3"}],
                 "unread": 1, "sent": [], "blocked": [], "online": 1}
        thread = {"name": "Sam", "e2e": True, "messages": [{"id": "m1", "from": "p3", "name": "Sam", "text": "hello there", "at": now - 60, "mine": False}]}

        def friends(body):
            a = body.get("action")
            if a == "decide":
                inbox["requests"] = []
                if body.get("accept"):
                    inbox["friends"].append({"id": "p2", "name": "Bro", "online": False, "e2e": True})
                return {"inbox": inbox}
            if a == "thread":
                inbox["conversations"][0]["unread"] = 0
                inbox["unread"] = 0
                return thread
            if a == "message":
                thread["messages"].append({"id": "m2", "text": body["text"], "at": _t.time(), "mine": True})
                return thread
            if a == "group_thread":
                return {"name": "Squad", "e2e": True, "messages": [{"id": "g1m", "from": "p3", "name": "Sam", "text": "gg everyone", "at": now - 120, "mine": False}]}
            return {"enabled": True, "me": inbox["me"], "inbox": inbox}
        page = self.open(pad=True, before=lambda p: _fake(p, calls, "friends", friends))
        self.ready(page)
        page.evaluate("async () => { S.friendsOn = true; await tvFriends(); }")
        self.until(page, "!!document.querySelector('[data-row=\"friends\"] [data-key=\"i:Incoming\"]')", 5)
        self.focus_tile(page, "friends", "i:Incoming")
        self.tap(page, 0)                                  # A: Incoming
        page.wait_for_selector(".tm-layer >> text=Friend requests")
        self.assertIn("Bro", page.inner_text(".tm-layer"))
        self.assertEqual("acc:p2", page.evaluate("document.activeElement.dataset.k"))
        self.tap(page, 0)                                  # A: Accept
        self.until(page, "!document.querySelector('[data-k=\"acc:p2\"]')", 5)
        self.assertIn({"action": "decide", "from": "p2", "accept": True}, calls["friends"])
        self.tap(page, 5)                                  # RB: Messages
        self.until(page, "document.querySelector('.tm-btn.tab.on').textContent.startsWith('Messages')", 3)
        page.evaluate("document.querySelector('.tm-layer [data-k=\"c:p3\"]').focus()")
        self.tap(page, 0)                                  # A: open the conversation with Sam
        page.wait_for_selector(".tm-msgs .tm-msg")
        self.assertIn("hello there", page.inner_text(".tm-msgs"))
        self.assertIn({"action": "thread", "friend": "p3"}, calls["friends"])
        self.tap(page, 3)                                  # Y: reply with the on-screen keyboard
        page.wait_for_selector(".tm-kb")
        self.tap(page, 0)                                  # A on the first key types it
        page.keyboard.type(" See you Tonight")
        self.assertIn("1 See you Tonight", page.inner_text(".tm-q"))
        page.evaluate("document.querySelector('.tm-key.primary').focus()")
        self.tap(page, 0)                                  # A: Send
        self.until(page, "document.querySelector('.tm-msgs') && document.querySelector('.tm-msgs').innerText.includes('See you Tonight')", 5)
        self.assertIn({"action": "message", "to": "p3", "text": "1 See you Tonight"}, calls["friends"])
        self.tap(page, 1)                                  # B: back to the friends sheet
        self.until(page, "!document.querySelector('.tm-msgs') && !!document.querySelector('.tm-tabs')", 3)
        page.evaluate("document.querySelector('.tm-layer [data-k=\"c:g:g1\"]').focus()")
        self.tap(page, 0)                                  # a group chat is readable too
        self.until(page, "document.querySelector('.tm-msgs') && document.querySelector('.tm-msgs').innerText.includes('gg everyone')", 5)
        self.assertIn("Sam", page.inner_text(".tm-msgs"))
        self.assertIn("Group: Squad", page.inner_text(".tm-layer:last-child h2"))
        self.assertEqual([], self.problems)

    # ---- 3c. a friend's server ----
    def test_join_a_friends_server_with_its_code(self):
        calls = {}
        answers = [{"connected": False, "message": "That server did not answer."}, {"connected": True}]
        page = self.open(pad=True, before=lambda p: _fake(p, calls, "server_connect", lambda b: answers.pop(0)))
        self.ready(page)
        self.focus_tile(page, "online", "i:joinsrv")
        self.tap(page, 0)
        page.wait_for_selector(".tm-kb")
        self.assertIn("Join a friend's server", page.inner_text(".tm-layer"))
        page.keyboard.type("lp-abcd-efgh")
        page.evaluate("document.querySelector('.tm-key.primary').focus()")
        self.tap(page, 0)                                  # Connect
        page.wait_for_selector(".tm-layer >> text=Could not connect")
        self.assertEqual({"code": "LP-ABCD-EFGH"}, calls["server_connect"][0])
        self.assertIn("did not answer", page.inner_text(".tm-layer"))
        self.tap(page, 0)                                  # Type the code again: the keyboard keeps what was typed
        page.wait_for_selector(".tm-kb")
        self.assertIn("LP-ABCD-EFGH", page.inner_text(".tm-q"))
        page.evaluate("document.querySelector('.tm-key.primary').focus()")
        self.tap(page, 0)
        page.wait_for_selector(".tm-layer >> text=Connected to your friend's server")
        self.assertEqual(2, len(calls["server_connect"]))
        self.assertEqual([], self.problems)

    # ---- 3d. the room ----
    def test_room_lobby_shows_ready_state_starts_and_closes(self):
        calls = {}
        room = {"role": "host", "game": "Alpha Quest", "console": "nes", "max_players": 4, "invite_code": "ABCDE-FGHIJ", "state": "waiting",
                "members": [{"name": "Al", "me": True, "role": "host", "ready": False}, {"name": "Bro", "role": "guest", "ready": True}],
                "launch": {"engine": "retroarch", "ready": True, "default_port": 55435}, "pending": [], "waitlist": [], "events": [], "new_events": []}
        live = {"room": room}

        def state(body):
            return {"room": live["room"], "waits": []}

        def start(body):
            room["start"] = {"id": "s1", "title": "Alpha Quest", "consented": ["Al"], "waiting_on": ["Bro"]}
            return {"room": room}

        def ready(body):
            room["members"][0]["ready"] = bool(body.get("ready", True))
            return {"room": room}

        def leave(body):
            live["room"] = None
            return {"room": None}

        def before(p):
            _fake(p, calls, "mp_state", state)
            _fake(p, calls, "mp_start", start)
            _fake(p, calls, "mp_launch", {"launched": "Alpha Quest", "relay": True})
            _fake(p, calls, "mp_ready", ready)
            _fake(p, calls, "mp_leave", leave)
            _fake(p, calls, "server_control", {"running": False})
        page = self.open(pad=True, before=before)
        self.ready(page)
        self.until(page, "!!S.room", 5)
        page.evaluate("tvRefreshRow('online')")
        self.focus_tile(page, "online", "i:Your room")
        self.tap(page, 0)
        page.wait_for_selector(".tm-members .tm-mem")
        text = page.inner_text(".tm-layer")
        for want in ("Hosting Alpha Quest", "ABCDE-FGHIJ", "Al (you)", "Bro", "Ready", "Not ready"):
            self.assertIn(want, text)
        self.assertEqual("start", page.evaluate("document.activeElement.dataset.k"))
        self.tap(page, 0)                                  # A: Start the match > asks first
        page.wait_for_selector(".tm-layer >> text=Start Alpha Quest for everyone?")
        self.assertNotIn("mp_start", calls)
        self.tap(page, 0)
        self.until(page, "!!document.querySelector('.tm-hint') && document.querySelector('.tm-layer').innerText.includes('Still deciding: Bro')", 5)
        self.assertEqual([{"consent": True}], calls["mp_start"])
        for _ in range(50):                                # the launch call follows the start answer
            if "mp_launch" in calls:
                break
            page.wait_for_timeout(100)
        self.assertEqual(1, len(calls["mp_launch"]))
        page.evaluate("document.querySelector('.tm-layer [data-k=\"ready\"]').focus()")
        self.tap(page, 0)                                  # I'm ready
        self.until(page, "document.querySelectorAll('.tm-mem.ready').length === 2", 5)
        self.assertEqual({"ready": True}, calls["mp_ready"][0])
        page.evaluate("document.querySelector('.tm-layer [data-k=\"leave\"]').focus()")
        self.tap(page, 0)                                  # Close the room > asks first
        page.wait_for_selector(".tm-layer >> text=Close the room?")
        self.tap(page, 0)
        self.until(page, "!document.querySelector('.tm-members') && S.room === null", 5)
        self.assertEqual(1, len(calls["mp_leave"]))
        self.assertEqual([], self.problems)

    # ---- 4. a page opened from TV mode works with the pad ----
    def test_a_page_from_tv_mode_is_driven_by_the_pad(self):
        page = self.open(pad=True)
        self.ready(page)
        self.go_row(page, "settings")
        page.keyboard.press("End")                         # All settings
        key = self.focused(page)
        page.evaluate("__press(0, true)")
        page.wait_for_timeout(400)
        page.evaluate("__press(0, false)")
        self.until(page, "!document.querySelector('#tvmode') && S.tab === 'settings'", 3)
        page.wait_for_timeout(300)
        self.assertIn("back to TV mode", page.inner_text("#tvback"))
        self.assertTrue(page.evaluate("document.documentElement.classList.contains('padnav')"))
        self.assertEqual(0, page.locator(".modal").count())            # the held A did not press anything on the page
        self.tap(page, 13)                                 # down: the focus goes into the page
        self.until(page, "document.querySelector('#main').contains(document.activeElement)", 3)
        first = page.evaluate("document.activeElement.outerHTML.slice(0, 120)")
        self.tap(page, 13)
        self.until(page, f"document.activeElement.outerHTML.slice(0, 120) !== {first!r}", 3)
        y = page.evaluate("scrollY")
        self.tap(page, 5)                                  # RB scrolls down
        self.until(page, f"scrollY > {y}", 3)
        self.tap(page, 4)                                  # LB scrolls back up
        # a dialog on the page is driven by the dialogs' own loop: B closes it and stays on the page
        page.evaluate("window.__answer = 'none'; void ask('A question?', 'Yes').then(v => { window.__answer = v; })")
        page.wait_for_selector(".modal")
        page.wait_for_timeout(200)
        self.tap(page, 1)
        self.until(page, "window.__answer === false", 3)
        page.wait_for_timeout(300)
        self.assertEqual("settings", page.evaluate("S.tab"))
        self.assertFalse(page.evaluate("TVM.on"))
        self.tap(page, 1)                                  # B: back to TV mode, on the same tile
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.until(page, f"(document.activeElement.dataset || {{}}).key === {key!r}", 5)
        self.assertFalse(page.evaluate("document.documentElement.classList.contains('padnav')"))
        self.assertEqual([], self.problems)

    # ---- 5, 6. Console mode is TV mode; the last page can be TV mode ----
    def test_console_mode_opens_tv_mode(self):
        page = self.open(start_page="home")
        page.wait_for_selector("text=Your emulators")
        self.assertNotIn("Console mode", page.inner_text("#nav"))
        page.click("#nav >> text=TV mode")                 # the tab that was Console mode
        self.ready(page)
        page.evaluate("exitTvMode()")
        self.until(page, "!document.querySelector('#tvmode')", 3)
        page.evaluate('nav("console")')                    # old links and saved settings that point at Console mode
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.assertEqual("tv", page.evaluate("async () => (await api('settings', {key: 'start_page', value: 'console'})).values.start_page"))
        self.assertEqual([], self.problems)

    def test_last_page_can_be_tv_mode(self):
        page = self.open(start_page="last")
        page.evaluate("async () => { await api('settings', {key: 'last_page', value: 'library'}); }")
        page.reload()
        page.wait_for_selector("#main .game")
        self.assertEqual(0, page.locator("#tvmode").count())
        page.keyboard.press("F11")
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.until(page, "S.settings.last_page === 'tv'", 3)
        page.reload()
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.assertEqual("tv", page.evaluate("async () => (await api('settings')).values.last_page"))
        self.assertEqual([], self.problems)


class TvBigLibraryTests(_TvApp):
    """More games than a row or the picker shows at once: a Show more tile instead of a silent cut."""
    LIBRARY = {"NES": [f"Game {i:03d} (USA).nes" for i in range(320)]}

    def test_rows_and_the_picker_show_more(self):
        page = self.open()
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.assertEqual(300, page.locator('#tvmode [data-row="con:nes"] .tm-tile[data-key^="g:"]').count())
        self.assertEqual(1, page.locator('#tvmode [data-row="con:nes"] [data-key="i:all:nes"]').count())
        page.evaluate("TVM.rows.find(r => r.id === 'con:nes').tiles.find(t => t.key === 'i:all:nes').act()")
        page.wait_for_selector(".tm-pick .tm-more")
        self.assertEqual(120, page.locator(".tm-pick .tm-tile:not(.tm-more)").count())
        page.click(".tm-pick .tm-more")
        self.until(page, "document.querySelectorAll('.tm-pick .tm-tile:not(.tm-more)').length === 240", 3)
        page.click(".tm-pick .tm-more")
        self.until(page, "document.querySelectorAll('.tm-pick .tm-tile:not(.tm-more)').length === 320", 3)
        self.assertEqual(0, page.locator(".tm-pick .tm-more").count())
        page.keyboard.press("Escape")
        page.keyboard.press("/")
        page.wait_for_selector(".tm-kb")
        page.keyboard.type("GAME")
        self.assertEqual(60, page.locator(".tm-results .tm-tile").count())
        self.assertIn("260 more matches", page.inner_text(".tm-results"))


class TvPadInputTests(_TvApp):
    """The one controller reader (padPoll): short taps, held directions, odd pads, several pads, lost focus, one press
    going to one place only, the input check and the "bring the window back" hint."""
    LIBRARY = {"NES": [f"Game {i:02d} (USA).nes" for i in range(12)], "SNES": ["Super Game (USA).sfc", "Other Game (USA).sfc"]}

    def ready(self, page):
        page.wait_for_selector("#tvmode.in .tm-tile")
        self.until(page, "document.activeElement && document.activeElement.classList.contains('tm-tile')")
        self.until(page, "PADHUB.layer === 'tv'", 3)

    def spy_moves(self, page):
        page.evaluate("window.__moves = []; const o = tvMove; tvMove = d => { __moves.push([d, performance.now()]); return o(d); }; true")

    def col(self, page):
        return page.evaluate("TVM.col[TVM.rows[TVM.r].id] || 0")

    def test_a_tap_of_one_read_counts_exactly_once(self):
        page = self.open(pad=True)
        self.ready(page)
        self.go_row(page, "con:nes")
        self.spy_moves(page)
        start = self.col(page)
        self.tap(page, 15)                                  # right, down for one read only
        page.wait_for_timeout(250)
        self.assertEqual([["right"]], page.evaluate("__moves.map(m => [m[0]])"))
        self.assertEqual(start + 1, self.col(page))
        for _ in range(3):                                  # quick taps one after another: each one counts
            self.tap(page, 15)
        page.wait_for_timeout(200)
        self.assertEqual(4, page.evaluate("__moves.length"))
        self.assertEqual(start + 4, self.col(page))
        self.assertEqual([], self.problems)

    def test_a_held_direction_repeats_after_a_pause(self):
        page = self.open(pad=True)
        self.ready(page)
        self.go_row(page, "con:nes")
        self.spy_moves(page)
        page.evaluate("__press(15, true)")
        page.wait_for_timeout(300)
        self.assertEqual(1, page.evaluate("__moves.length"))          # not yet repeating
        page.wait_for_timeout(700)
        page.evaluate("__press(15, false)")
        times = page.evaluate("__moves.map(m => m[1])")
        self.assertGreaterEqual(len(times), 4, times)
        self.assertLessEqual(len(times), 9, times)
        self.assertGreaterEqual(times[1] - times[0], 330)              # the first repeat waits about 380 ms
        gaps = [b - a for a, b in zip(times[1:], times[2:])]
        self.assertTrue(all(80 <= g <= 260 for g in gaps), gaps)       # then about every 110 ms
        n = len(times)
        page.wait_for_timeout(400)
        self.assertEqual(n, page.evaluate("__moves.length"))           # let go: it stops
        self.assertEqual([], self.problems)

    def test_a_pad_without_the_standard_layout_and_a_hat_d_pad_navigates(self):
        page = self.open(pad=True)
        # a DirectInput pad as Chromium on Windows shows it: no "standard" mapping, 12 buttons, the D-pad as axis 9
        page.evaluate("__plug(0, __mkpad(0, '0e8f-310d-USB Gamepad', '', 12, [0, 0, 0, 0, 0, 0, 0, 0, 0, 3.2857]))")
        self.ready(page)
        self.go_row(page, "con:nes")
        self.spy_moves(page)
        hat = """async v => { const poll = async () => { const k = PADHUB.polls; while (PADHUB.polls === k) await new Promise(r => setTimeout(r, 1)); };
                  __pads[0].axes[9] = v; await poll(); __pads[0].axes[9] = 3.2857; await poll(); }"""
        page.evaluate(hat, -0.4286)                          # right
        page.evaluate(hat, 0.7143)                           # left
        page.evaluate(hat, 0.1429)                           # down
        page.wait_for_timeout(200)
        self.assertEqual(["right", "left", "down"], page.evaluate("__moves.map(m => m[0])"))
        self.assertIn("hat switch on axis 9", page.evaluate("padDebug(true), document.querySelector('#paddebug').innerText"))
        page.evaluate("padDebug(false)")
        # its stick moves too, and raw button 0 presses
        page.evaluate("__pads[0].axes[0] = 0.9")
        self.until(page, "__moves.length === 4", 3)
        page.evaluate("__pads[0].axes[0] = 0")
        self.go_row(page, "con:nes")
        self.tap(page, 0)
        page.wait_for_selector(".tm-layer .tm-details")
        self.assertEqual([], self.problems)

    def test_the_second_pad_drives_tv_mode_and_dialogs(self):
        page = self.open(pad=True)
        page.evaluate("__plug(1, __mkpad(1, 'Second Pad (STANDARD GAMEPAD Vendor: 054c Product: 09cc)', 'standard', 17, [0, 0, 0, 0]))")
        self.ready(page)
        self.go_row(page, "con:nes")
        start = self.col(page)
        self.tap(page, 15, pad=1)
        self.until(page, f"(TVM.col[TVM.rows[TVM.r].id] || 0) === {start + 1}", 3)
        page.evaluate("__press(0, true, 0)")                 # the first pad holds A: the second pad's A still counts
        self.tap(page, 0, pad=1)
        page.wait_for_selector(".tm-layer .tm-details")
        page.evaluate("__press(0, false, 0)")
        page.evaluate("window.__answer = 'none'; void ask('A question?', 'Yes').then(v => { window.__answer = v; })")
        page.wait_for_selector(".modal")
        self.until(page, "PADHUB.layer instanceof Element", 3)
        self.tap(page, 1, pad=1)                             # B on the second pad cancels the dialog (it only listened to the first)
        self.until(page, "window.__answer === false", 3)
        page.wait_for_timeout(200)
        self.assertEqual(1, page.locator(".tm-layer .tm-details").count())      # and only the dialog
        self.assertEqual([], self.problems)

    def test_lost_focus_comes_back_on_the_next_press(self):
        page = self.open(pad=True)
        self.ready(page)
        self.go_row(page, "con:nes")
        self.tap(page, 15)
        key = self.focused(page)
        page.evaluate("document.activeElement.blur()")
        self.assertEqual("BODY", page.evaluate("document.activeElement.tagName"))
        self.tap(page, 15)                                   # the first press shows where you are, on the same tile
        self.until(page, "document.activeElement.classList.contains('tm-tile')", 3)
        self.assertEqual(key, self.focused(page))
        self.tap(page, 15)                                   # and the next one moves
        self.until(page, f"(document.activeElement.dataset.key || '') !== {key!r}", 3)
        # in a sheet: A finds the focus again instead of doing nothing
        self.tap(page, 0)
        page.wait_for_selector(".tm-layer .tm-details")
        page.evaluate("document.activeElement.blur()")
        self.tap(page, 0)
        self.until(page, "document.querySelector('.tm-layer').contains(document.activeElement)", 3)
        self.assertEqual(1, page.locator(".tm-layer").count())
        # in a dialog too
        page.evaluate("void ask('A question?', 'Yes')")
        page.wait_for_selector(".modal")
        page.wait_for_timeout(100)
        page.evaluate("document.activeElement.blur()")
        self.tap(page, 13)
        self.until(page, "document.querySelector('.modal').contains(document.activeElement)", 3)
        self.assertEqual([], self.problems)

    def test_one_press_goes_to_one_place_only(self):
        calls = {}
        page = self.open(pad=True, before=lambda p: _fake(p, calls, "quit", {}))
        self.ready(page)
        self.go_row(page, "power")
        page.keyboard.press("End")
        self.assertEqual("i:Quit Legacy Player", self.focused(page))
        self.tap(page, 0)                                    # a short A opens the question and does not answer it
        page.wait_for_selector(".modal")
        page.wait_for_timeout(300)
        self.assertIn("Quit Legacy Player?", page.inner_text(".modal"))
        self.assertNotIn("quit", calls)
        r = page.evaluate("TVM.r")
        page.evaluate("__press(1, true)")                    # B held: it cancels the question...
        self.until(page, "!document.querySelector('.modal')", 3)
        page.wait_for_timeout(700)                           # ...and, still held, does not also move TV mode back a row
        page.evaluate("__press(1, false)")
        page.wait_for_timeout(100)
        self.assertEqual(r, page.evaluate("TVM.r"))
        self.assertEqual(0, page.locator(".tm-layer").count())
        log = page.evaluate("PADHUB.log.join('\\n')")
        self.assertEqual(1, log.count("B  pad 0"), log)
        self.assertIn("→  dialog", log)
        self.assertNotIn("quit", calls)
        self.assertTrue(page.evaluate("TVM.on"))
        self.assertEqual([], self.problems)

    def test_a_pad_the_browser_shows_on_its_first_press(self):
        page = self.open(pad=True)
        page.evaluate("__pads[0] = null")
        self.ready(page)
        self.until(page, "document.querySelector('#tm-pad').textContent.includes('Press any button')", 3)
        self.go_row(page, "con:nes")
        page.evaluate("__plug(0, __pad); __press(0, true)")          # the press that makes the browser show it
        page.wait_for_timeout(300)
        page.evaluate("__press(0, false)")
        page.wait_for_timeout(100)
        self.assertEqual(0, page.locator(".tm-layer").count())         # was not taken as A
        self.tap(page, 0)                                              # the next one is
        page.wait_for_selector(".tm-layer .tm-details")
        self.assertEqual([], self.problems)

    def test_a_players_own_mapping_does_not_move_the_menus(self):
        page = self.open(pad=True)
        self.ready(page)
        # the player swapped A and X for games
        page.evaluate("""async () => { S.P = await api('pad_save', {id: __pad.id, name: 'Test Pad', standard: true,
                          bindings: {'0': {t: 'b', i: 2}, '2': {t: 'b', i: 0}}}); }""")
        self.go_row(page, "con:nes")
        self.tap(page, 0)                                              # A is still A in the menus
        page.wait_for_selector(".tm-layer .tm-details")
        page.evaluate("async () => { await api('pad_delete', {id: __pad.id}); }")
        self.assertEqual([], self.problems)

    def test_back_and_y_show_the_input_check(self):
        page = self.open(pad=True)
        self.ready(page)
        page.evaluate("__press(8, true); __press(3, true)")
        page.wait_for_selector("#paddebug", timeout=5000)
        page.evaluate("__press(8, false); __press(3, false)")
        text = page.inner_text("#paddebug")
        for want in ("Test Pad", "layout: standard", "Presses go to: TV mode", "kept (hold Back + Y"):
            self.assertIn(want, text)
        self.assertEqual(0, page.locator(".tm-layer").count())         # the Y did not open the search
        self.tap(page, 15)
        self.until(page, "document.querySelector('#paddebug').innerText.includes('Right  pad 0  →  TV mode')", 3)
        page.click("#paddebug .x")
        self.assertEqual(0, page.locator("#paddebug").count())
        self.assertEqual([], self.problems)

    def test_a_window_behind_others_says_how_to_bring_it_back(self):
        page = self.open(pad=True)
        self.ready(page)
        self.assertEqual(0, page.locator("#padfocus").count())
        page.evaluate("document.hasFocus = () => false")
        page.wait_for_selector("#padfocus", timeout=3000)
        self.assertIn("Alt+Tab", page.inner_text("#padfocus"))
        page.evaluate("document.hasFocus = () => true")
        self.until(page, "!document.querySelector('#padfocus')", 3)
        self.assertEqual([], self.problems)

    def test_tiles_do_not_all_animate_at_once(self):
        page = self.open()
        page.wait_for_selector("#tvmode.in .tm-tile")
        page.wait_for_timeout(300)
        busy = page.evaluate("""document.getAnimations().filter(a => a.playState === 'running' && a.effect && a.effect.target &&
                                a.effect.target.closest && (a.effect.target.closest('#tvmode .tm-rows') || a.effect.target.closest('#main, .chrome'))).length""")
        self.assertLessEqual(busy, 6)


if __name__ == "__main__":
    unittest.main()
