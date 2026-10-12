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
    def open(self, start_page="tv", intro=False, pad=False, width=1280, height=720):
        """A fresh window of the app with these settings saved first (as the app would have them at start-up)."""
        page = self.context.new_page()
        page.set_viewport_size({"width": width, "height": height})
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

    def rows(self, page):
        return page.evaluate("[...document.querySelectorAll('#tvmode .tm-row')].map(r => r.dataset.row)")

    def go_row(self, page, row):
        """Focus the first tile of a row with the keyboard (Tab: next row)."""
        for _ in range(40):
            if page.evaluate("(document.activeElement.closest && document.activeElement.closest('.tm-row') || {dataset: {}}).dataset.row") == row:
                return
            page.keyboard.press("Tab")
        self.fail("no row " + row)

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
        self.assertIn("still need", page.inner_text(".tm-layer"))     # the NES games need an emulator

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


if __name__ == "__main__":
    unittest.main()
