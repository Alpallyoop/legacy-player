"""Behind a reverse proxy on the same computer every request comes from loopback, which is never limited: with
--trusted-proxy the friends service counts new identities per the proxy's X-Forwarded-For address instead."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from server.social import SocialService
from server.social.__main__ import FriendsHTTPServer, make_handler
from server.http_guard import AddressWindow


class TrustedProxy(unittest.TestCase):
    def serve(self, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        service = SocialService(Path(tmp.name) / "social")
        httpd = FriendsHTTPServer(("127.0.0.1", 0), make_handler(service, "local-key", hello_limit=AddressWindow(2, 3600), **kw))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.shutdown)
        return f"http://127.0.0.1:{httpd.server_address[1]}/"

    def hello(self, url, forwarded=None, name="Al"):
        headers = {"Content-Type": "application/json"}
        if forwarded:
            headers["X-Forwarded-For"] = forwarded
        req = urllib.request.Request(url, json.dumps({"op": "hello", "name": name}).encode(), headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as exc:
            return exc.code

    def test_without_the_option_a_proxy_hides_every_client(self):
        url = self.serve()
        self.assertEqual([200] * 6, [self.hello(url, "203.0.113.%d" % i) for i in range(6)])      # all "this computer": never limited

    def test_with_the_option_each_forwarded_address_has_its_own_limit(self):
        url = self.serve(trusted_proxy=True)
        self.assertEqual([200, 200, 429], [self.hello(url, "203.0.113.9") for _ in range(3)])
        self.assertEqual(200, self.hello(url, "203.0.113.10"))                                   # another client is not affected
        self.assertEqual(429, self.hello(url, "198.51.100.1, 203.0.113.9"))                       # only the LAST hop (the proxy's) counts
        self.assertEqual(200, self.hello(url, "not an address"))                                  # junk falls back to loopback: unlimited, as before


if __name__ == "__main__":
    unittest.main()
