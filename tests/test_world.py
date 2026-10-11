"""The Legacy Player World themes: day and night follow the clock unless the player picks one, holiday towns dress the
app up during their holiday, and the tray follows along."""
import datetime
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from launcher import world
from launcher.catalog import SETTINGS_SCHEMA

try:
    from playwright.sync_api import sync_playwright
except ImportError:      # pragma: no cover
    sync_playwright = None

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "launcher" / "ui" / "index.html").read_text(encoding="utf-8")


def at(hour, minute=0, month=10, day=10):
    return time.mktime((2026, month, day, hour, minute, 0, 0, 0, -1))


class DayAndNight(unittest.TestCase):
    def test_follow_my_clock_switches_at_seven(self):
        self.assertEqual("night", world.time_now("auto", at(6, 59)))
        self.assertEqual("day", world.time_now("auto", at(7, 0)))
        self.assertEqual("day", world.time_now("auto", at(18, 59)))
        self.assertEqual("night", world.time_now("auto", at(19, 0)))
        self.assertEqual("night", world.time_now("night", at(12)))
        self.assertEqual("day", world.time_now("day", at(23)))

    def test_light_means_the_light_theme_or_a_world_place_by_day(self):
        noon = at(12)            # 10 October: no holiday (spooky season needs Seasonal themes)
        self.assertTrue(world.looks_light({"theme": "light"}, noon))
        self.assertFalse(world.looks_light({"theme": "dark"}, noon))
        self.assertTrue(world.looks_light({"theme": "harbor", "time_of_day": "day"}, noon))
        self.assertFalse(world.looks_light({"theme": "harbor", "time_of_day": "night"}, noon))
        self.assertTrue(world.looks_light({"theme": "frost", "time_of_day": "auto"}, noon))

    def test_every_place_is_a_theme_choice_and_the_page_draws_it(self):
        for biome, name in world.BIOMES.items():
            self.assertIn(biome, SETTINGS_SCHEMA["theme"]["choices"])
            self.assertIn(f'id:"{biome}",name:"{name}"', PAGE)       # the colours and the scene exist for it
            self.assertIn(f"\n  {biome}:{{still(", PAGE)
        self.assertEqual(list(world.TIMES), SETTINGS_SCHEMA["time_of_day"]["choices"])
        self.assertIn("scene", SETTINGS_SCHEMA["background"]["choices"])

    def test_contrast_checker_covers_every_place_and_holiday_town(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("contrast_check", ROOT / "tools" / "contrast_check.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        self.assertEqual({f"{b}:{t}" for b in world.BIOMES for t in ("day", "night")}, set(tool.WORLD))


class Holidays(unittest.TestCase):
    def test_the_calendar(self):
        h = lambda m, d, s=False: (world.holiday_for(m, d, s) or {}).get("theme")
        self.assertIsNone(h(10, 23))                       # spooky season is opt-in
        self.assertEqual("spooky", h(10, 1, True))
        self.assertEqual("spooky", h(10, 23, True))
        self.assertEqual("pumpkin", h(10, 24))
        self.assertEqual("pumpkin", h(10, 31, True))       # Halloween week wins over spooky season
        self.assertEqual("pumpkin", h(11, 1))
        self.assertIsNone(h(11, 2))
        self.assertIsNone(h(9, 30, True))
        self.assertIsNone(h(12, 17))
        self.assertEqual("winterlights", h(12, 18))
        self.assertEqual("winterlights", h(12, 30))
        self.assertEqual("newyear", h(12, 31))
        self.assertEqual("newyear", h(1, 1))
        self.assertIsNone(h(1, 2))
        for x in world.HOLIDAYS:
            self.assertIn(x["theme"], world.HOLIDAY_BIOMES)

    def test_a_holiday_shows_its_town_without_touching_the_saved_theme(self):
        halloween, after = at(20, month=10, day=28), at(20, month=11, day=2)
        mine = {"theme": "harbor", "time_of_day": "day"}
        self.assertEqual("pumpkin", world.shown_theme(mine, halloween))
        self.assertEqual("harbor", mine["theme"])
        self.assertEqual("harbor", world.shown_theme(mine, after))          # the holiday ended: theirs is back
        self.assertEqual("harbor", world.shown_theme(dict(mine, holiday_themes=False), halloween))
        self.assertEqual("dark", world.shown_theme({"theme": "dark"}, at(12, month=10, day=5)))
        self.assertEqual("spooky", world.shown_theme({"theme": "dark", "seasonal_themes": True}, at(12, month=10, day=5)))
        self.assertTrue(world.looks_light({"theme": "dark", "time_of_day": "day"}, halloween))   # Pumpkin Town by day
        self.assertFalse(world.looks_light({"theme": "dark", "time_of_day": "day", "holiday_themes": False}, halloween))

    def test_settings(self):
        self.assertIs(True, SETTINGS_SCHEMA["holiday_themes"]["default"])
        self.assertIs(False, SETTINGS_SCHEMA["seasonal_themes"]["default"])
        self.assertTrue(SETTINGS_SCHEMA["holiday_prompt_seen"]["hidden"])
        self.assertEqual("tv", SETTINGS_SCHEMA["start_page"]["default"])
        self.assertEqual(["tv", "home", "library", "servers", "console", "friends", "last"], SETTINGS_SCHEMA["start_page"]["choices"])
        self.assertIs(True, SETTINGS_SCHEMA["tv_intro"]["default"])

    def test_page_and_python_share_one_calendar(self):
        table = PAGE[PAGE.index("const HOLIDAYS=["):PAGE.index("function holidayFor(")]
        found = re.findall(r'\{id:"(\w+)",theme:"(\w+)",from:\[(\d+),(\d+)\],to:\[(\d+),(\d+)\](,seasonal:true)?', table)
        self.assertEqual([(x["id"], x["theme"], x["start"], x["end"], x["seasonal"]) for x in world.HOLIDAYS],
                         [(i, t, (int(a), int(b)), (int(c), int(d)), bool(s)) for i, t, a, b, c, d, s in found])


class StartAndNav(unittest.TestCase):
    def test_tabs_are_home_library_servers_console_setup(self):
        line = PAGE[PAGE.index("const PRIMARY="):].split("\n", 1)[0]
        self.assertEqual(["home", "library", "servers", "console", "setup"], re.findall(r'\["(\w+)","', line))

    def test_start_page_hook_for_tv_mode(self):
        self.assertIn('start==="tv"&&!S.tvBooted&&typeof enterTvMode==="function")enterTvMode({intro:true})', PAGE)


@unittest.skipUnless(sync_playwright, "Playwright is not installed")
class InThePage(unittest.TestCase):
    """The real page: holidayFor() agrees with launcher/world.py on every day of a leap year, the one-time holiday question,
    the pixel title, and opening on the chosen start page."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        (base / "games" / "NES").mkdir(parents=True)
        (base / "games" / "NES" / "Alpha Quest (USA).nes").write_bytes(b"NES\x1a" + b"\0" * 64)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        keep = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "LANG", "PYTHONPATH", "LOCALAPPDATA", "APPDATA")
        env = {k: os.environ[k] for k in keep if k in os.environ}
        env["LEGACY_PLAYER_NO_BACKGROUND"] = "1"
        cls.proc = subprocess.Popen([sys.executable, "-m", "launcher", "--data-dir", str(base / "data"), "--games", str(base / "games"),
                                     "--port", str(port), "--no-browser"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        line, deadline = "", time.time() + 30
        while time.time() < deadline and "http://" not in line:
            line = cls.proc.stdout.readline()
        found = re.search(r"http://\S+", line)
        if not found:
            cls.proc.kill()
            raise RuntimeError("the app did not start: " + line)
        cls.url = found.group(0)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()
        cls.context = cls.browser.new_context(viewport={"width": 1280, "height": 860})
        first = cls.context.new_page()
        first.goto(cls.url)                      # the one-time ?k= address sets the session cookie for this context
        first.wait_for_selector("#nav button", state="attached")
        first.close()
        cls.home = cls.url.split("?", 1)[0]

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.proc.kill()
        cls.proc.wait(5)
        cls.tmp.cleanup()

    def open(self, when=None, settings=None):
        page = self.context.new_page()
        page.set_default_timeout(20000)
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto(self.home)
        page.wait_for_selector("#nav button", state="attached")
        base = {"setup_done": True, "holiday_themes": True, "seasonal_themes": False, "holiday_prompt_seen": False,
                "theme": "harbor", "start_page": "home"}
        base.update(settings or {})
        page.evaluate("async s => { for (const [k, v] of Object.entries(s)) await api('settings', {key: k, value: v}) }", base)
        if when:
            page.clock.set_system_time(when)
        page.reload()
        page.wait_for_selector("#nav button", state="attached")
        page.wait_for_timeout(600)
        return page

    def test_holiday_for_matches_python_every_day(self):
        page = self.open()
        days = [datetime.date(2024, 1, 1) + datetime.timedelta(days=i) for i in range(366)]
        got = page.evaluate("""days => days.map(([y, m, d]) => [false, true].map(s => {
            const x = holidayFor(new Date(y, m - 1, d, 12), {seasonal: s}); return x ? x.theme : null }))""",
                            [[d.year, d.month, d.day] for d in days])
        for d, (plain, seasonal) in zip(days, got):
            want = [(world.holiday_for(d.month, d.day, s) or {}).get("theme") for s in (False, True)]
            self.assertEqual(want, [plain, seasonal], d.isoformat())
        page.close()

    def test_halloween_dresses_up_once_and_use_my_own_theme_sticks(self):
        page = self.open(datetime.datetime(2026, 10, 28, 20, 0))
        page.wait_for_selector("#holidayask")
        self.assertEqual("pumpkin", page.evaluate("document.documentElement.dataset.theme"))
        self.assertIn("It's Halloween week", page.inner_text("#holidayask"))
        self.assertEqual("harbor", page.evaluate("api('settings').then(r => r.values.theme)"))    # saved theme untouched
        page.click("#holidayask button:has-text(\"Use my own theme\")")
        page.wait_for_function("() => document.documentElement.dataset.theme === 'harbor'")
        page.wait_for_timeout(300)
        v = page.evaluate("api('settings').then(r => r.values)")
        self.assertEqual((False, True, "harbor"), (v["holiday_themes"], v["holiday_prompt_seen"], v["theme"]))
        page.reload()
        page.wait_for_selector("#nav button", state="attached")
        page.wait_for_timeout(2200)
        self.assertIsNone(page.query_selector("#holidayask"))
        self.assertEqual("harbor", page.evaluate("document.documentElement.dataset.theme"))
        self.assertEqual([], self.errors)
        page.close()

    def test_keep_is_remembered_and_the_theme_returns_after_the_holiday(self):
        page = self.open(datetime.datetime(2026, 12, 20, 10, 0))
        page.wait_for_selector("#holidayask")
        self.assertEqual("winterlights", page.evaluate("document.documentElement.dataset.theme"))
        page.click("#holidayask button:has-text(\"Keep holiday themes\")")
        page.wait_for_timeout(500)
        self.assertEqual([True, True], page.evaluate("api('settings').then(r => [r.values.holiday_themes, r.values.holiday_prompt_seen])"))
        page.close()
        page = self.open(datetime.datetime(2027, 1, 2, 10, 0), {"holiday_prompt_seen": True})
        self.assertEqual("harbor", page.evaluate("document.documentElement.dataset.theme"))
        page.close()
        page = self.open(datetime.datetime(2026, 10, 5, 10, 0), {"holiday_prompt_seen": True, "seasonal_themes": True})
        self.assertEqual("spooky", page.evaluate("document.documentElement.dataset.theme"))
        page.close()

    def test_pixel_title_and_start_page(self):
        page = self.open(datetime.datetime(2026, 6, 1, 12, 0), {"start_page": "servers"})
        page.wait_for_selector("#srvlive")
        self.assertEqual("servers", page.evaluate("S.tab"))
        el = page.evaluate("(() => { const e = pixelTitle('Hi, Ana!', {tag: 'h2'}); return [e.tagName, e.getAttribute('aria-label'), e.querySelectorAll('svg').length] })()")
        self.assertEqual(["H2", "Hi, Ana!", 2], el)
        page.evaluate("nav('home')")
        page.wait_for_selector(".hero .pxtitle")
        self.assertTrue(page.evaluate("document.querySelector('.hero h1.pxtitle').getAttribute('aria-label').startsWith('Welcome back, ')"))
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(300)
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
        self.assertEqual([], self.errors)
        page.close()


if __name__ == "__main__":
    unittest.main()
