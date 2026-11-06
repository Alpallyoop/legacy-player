"""Drag a game onto a collection or Favorites, the way Steam's library does it (the cover follows the pointer, a bar offers
'remove', 'favorites' and 'drag and hold to view all collections'). Runs the real page in a headless browser with a pretend
library; skipped when Playwright is not installed."""
import unittest

from tests.test_tv_mode import _TvApp, sync_playwright

# a real drag cannot be recorded in a headless browser, so the page's own handlers are driven with the events a drag makes
DRAG_JS = """async ([gid, targetSel, kind]) => {
  const dt = new DataTransfer();
  const card = document.querySelector(`.game[data-gid="${gid}"]`);
  card.dispatchEvent(new DragEvent('dragstart', {bubbles: true, cancelable: true, dataTransfer: dt}));
  const target = document.querySelector(targetSel);
  if (!target) return {missing: true, types: [...dt.types]};
  for (const t of ['dragenter', 'dragover']) target.dispatchEvent(new DragEvent(t, {bubbles: true, cancelable: true, dataTransfer: dt}));
  if (kind === 'drop') target.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt}));
  return {types: [...dt.types]};
}"""


@unittest.skipUnless(sync_playwright, "Playwright is not installed")
class LibraryDragTests(_TvApp):
    LIBRARY = {"NES": ["Alpha Quest (USA).nes", "Beta Blast (USA).nes", "Castle Climber (USA).nes"]}

    def library(self):
        page = self.open(start_page="home", width=1280, height=800)
        page.evaluate("nav('library')")
        page.wait_for_selector(".game[data-gid]")
        return page

    def gid(self, page, title):
        return page.evaluate("t => [...document.querySelectorAll('.game')].find(c => c.textContent.includes(t)).dataset.gid", title)

    def api(self, page, name, body):
        return page.evaluate("async ([n, b]) => api(n, b)", [name, body])

    def test_cards_can_be_dragged_and_hidden_games_cannot(self):
        page = self.library()
        self.assertEqual("true", page.get_attribute(".game[data-gid]", "draggable"))
        self.assertEqual(3, page.evaluate("document.querySelectorAll('.game[draggable=true]').length"))
        page.evaluate("S.hiddenView = true; go()")
        page.wait_for_selector("#backtogames")
        self.assertEqual(0, page.evaluate("document.querySelectorAll('.game[draggable]').length"))      # hidden games stay put
        self.assertEqual([], self.problems)

    def test_dragging_shows_the_bar_with_favorites_and_the_hold_zone(self):
        page = self.library()
        gid = self.gid(page, "Alpha Quest")
        out = page.evaluate(DRAG_JS, [gid, "#dragbar .dz.hold", "over"])
        self.assertIn("application/x-legacy-player-game", out["types"])
        self.assertEqual(1, page.locator("#dragbar").count())
        text = page.inner_text("#dragbar")
        self.assertIn("DRAG and HOLD HERE", text)
        self.assertIn("to view all collections", text)
        self.assertIn("to FAVORITES", text)
        self.assertNotIn("DRAG HERE to remove", text)                    # not looking at a collection or at Favorites
        self.assertEqual(gid, page.evaluate("DRAG.g.id"))
        page.evaluate("libDragEnd()")
        self.assertEqual(0, page.locator("#dragbar").count())
        self.assertEqual([], self.problems)

    def test_drop_on_favorites_zone_and_on_a_collection_chip(self):
        page = self.library()
        gid = self.gid(page, "Alpha Quest")
        self.api(page, "collections", {"action": "create", "name": "Co-op nights"})
        page.evaluate("nav('library')")
        page.wait_for_selector("#colchips .chip:has-text('Co-op nights')")
        page.evaluate(DRAG_JS, [gid, "#dragbar .dz.fav", "drop"])
        self.until(page, "document.querySelector('#toasts').textContent.includes('added to Favorites')", 5)
        self.assertEqual(1, len(self.api(page, "library", {"favorites": True})["games"]))
        page.wait_for_selector(".game[data-gid]")
        page.evaluate("document.querySelectorAll('#colchips .chip').forEach(c => { if (c.textContent.startsWith('Co-op')) c.id = 'coopchip'; })")
        page.evaluate(DRAG_JS, [self.gid(page, "Beta Blast"), "#coopchip", "drop"])
        self.until(page, "document.querySelector('#toasts').textContent.includes('added to “Co-op nights”')", 5)
        self.assertEqual(1, self.api(page, "collections", {})["collections"][0]["count"])
        self.assertEqual([], self.problems)

    def test_hold_opens_the_list_of_collections_and_dropping_there_adds(self):
        page = self.library()
        self.api(page, "collections", {"action": "create", "name": "To finish"})
        page.evaluate("nav('library')")
        page.wait_for_selector("#colchips .chip:has-text('To finish')")
        gid = self.gid(page, "Castle Climber")
        page.evaluate(DRAG_JS, [gid, "#dragbar .dz.hold", "over"])
        page.wait_for_selector("#dragcols", timeout=3000)                  # opens by itself after the short hold
        self.assertIn("To finish", page.inner_text("#dragcols"))
        self.assertIn("New collection", page.inner_text("#dragcols"))
        page.evaluate("""() => {
          const dt = new DataTransfer(); dt.setData('application/x-legacy-player-game', DRAG.g.id);
          const row = [...document.querySelectorAll('#dragcols .dz.row')].find(r => r.textContent.includes('To finish'));
          for (const t of ['dragenter', 'dragover', 'drop']) row.dispatchEvent(new DragEvent(t, {bubbles: true, cancelable: true, dataTransfer: dt}));
        }""")
        self.until(page, "document.querySelector('#toasts').textContent.includes('added to “To finish”')", 5)
        self.assertEqual(1, self.api(page, "collections", {})["collections"][0]["count"])
        self.assertEqual(0, page.locator("#dragbar, #dragcols").count())      # the bar goes away once dropped
        self.assertEqual([], self.problems)

    def test_remove_zone_inside_a_collection_and_inside_favorites(self):
        page = self.library()
        gid = self.gid(page, "Alpha Quest")
        self.api(page, "collections", {"action": "create", "name": "Childhood"})
        self.api(page, "collections", {"action": "add", "name": "Childhood", "id": gid})
        page.evaluate("S.collection = 'Childhood'; go()")
        page.wait_for_selector(".game[data-gid]")
        page.evaluate(DRAG_JS, [gid, "#dragbar .dz.rm", "over"])
        text = page.inner_text("#dragbar")
        self.assertIn("DRAG HERE to remove", text)
        self.assertIn("CHILDHOOD", text)
        page.evaluate("""() => { const dt = new DataTransfer(); dt.setData('application/x-legacy-player-game', DRAG.g.id);
          const z = document.querySelector('#dragbar .dz.rm'); z.dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt})); }""")
        self.until(page, "document.querySelector('#toasts').textContent.includes('removed from “Childhood”')", 5)
        self.assertEqual(0, self.api(page, "collections", {})["collections"][0]["count"])
        # Favorites view
        self.api(page, "favorite", {"id": gid, "favorite": True})
        page.evaluate("S.collection = null; S.fav = true; go()")
        page.wait_for_selector(".game[data-gid]")
        page.evaluate(DRAG_JS, [gid, "#dragbar .dz.rm", "over"])
        self.assertIn("FAVORITES", page.inner_text("#dragbar"))
        page.evaluate("""() => { const dt = new DataTransfer(); dt.setData('application/x-legacy-player-game', DRAG.g.id);
          document.querySelector('#dragbar .dz.rm').dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt})); }""")
        self.until(page, "document.querySelector('#toasts').textContent.includes('removed from Favorites')", 5)
        self.assertEqual(0, len(self.api(page, "library", {"favorites": True})["games"]))
        self.assertEqual([], self.problems)

    def test_a_drag_from_outside_does_nothing_and_never_navigates(self):
        page = self.library()
        self.api(page, "collections", {"action": "create", "name": "Mine"})
        page.evaluate("nav('library')")
        page.wait_for_selector("#colchips .chip:has-text('Mine')")
        before = page.url
        result = page.evaluate("""() => {
          const dt = new DataTransfer(); dt.setData('text/plain', 'C:\\\\Windows\\\\win.ini'); dt.setData('text/uri-list', 'file:///C:/Windows/win.ini');
          const chip = [...document.querySelectorAll('#colchips .chip')].find(c => c.textContent.includes('Mine'));
          const over = new DragEvent('dragover', {bubbles: true, cancelable: true, dataTransfer: dt}); chip.dispatchEvent(over);
          const drop = new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt}); chip.dispatchEvent(drop);
          return {overPrevented: over.defaultPrevented, dropPrevented: drop.defaultPrevented, effect: dt.dropEffect, chipHot: chip.classList.contains('droptarget')};
        }""")
        self.assertEqual("none", result["effect"])                         # nothing may be dropped here...
        self.assertTrue(result["dropPrevented"])                           # ...and the window must not open the dropped file
        self.assertFalse(result["chipHot"])
        self.assertEqual(before, page.url)
        self.assertEqual(0, self.api(page, "collections", {})["collections"][0]["count"])

    def test_escape_cancels_the_drag_bar(self):
        page = self.library()
        page.evaluate(DRAG_JS, [self.gid(page, "Alpha Quest"), "#dragbar .dz.hold", "over"])
        self.assertEqual(1, page.locator("#dragbar").count())
        page.keyboard.press("Escape")
        self.assertEqual(0, page.locator("#dragbar").count())


if __name__ == "__main__":
    unittest.main()
