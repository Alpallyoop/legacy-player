"""The launcher's own page (audit 2026-11-04): a tight Content-Security-Policy, covers not cached (their address
carries the run's token), connections time out, and the page only sets https or same-server links."""
import unittest
from pathlib import Path

from launcher import web


class LocalPage(unittest.TestCase):
    def test_csp_shuts_framing_base_forms_and_plugins(self):
        for part in ("frame-ancestors 'none'", "base-uri 'none'", "form-action 'none'", "object-src 'none'", "connect-src 'self'"):
            self.assertIn(part, web.CSP)

    def test_covers_are_not_cached_and_idle_connections_end(self):
        src = Path(web.__file__).read_text(encoding="utf-8")
        self.assertNotIn("max-age=86400", src)
        self.assertIn("timeout = 60", src)

    def test_links_go_through_safe_url(self):
        ui = (Path(web.__file__).parent / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn("function safeUrl(", ui)
        self.assertIn('&&!safeUrl(v,k))continue', ui)
        self.assertNotIn('if(!r)window.open(', ui)


if __name__ == "__main__":
    unittest.main()
