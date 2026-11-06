"""The launcher's own page server, second 2026-11 stress test: a request from another site is refused, the media type is
read exactly, an absurdly nested body is an error not a crash, the page tells the browser not to send referrers, and a
text such as "false" is not a yes for a destructive action."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from launcher import web
from launcher.app import LauncherApp


class LocalServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app = LauncherApp(Path(cls.tmp.name) / "data")
        cls.token = "t" * 32
        cls.httpd = web.make_server(0, False)
        cls.port = cls.httpd.server_address[1]
        cls.httpd.RequestHandlerClass = web.make_handler(cls.app, cls.token, lambda: cls.httpd.server_address[1], web.Launch())
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.tmp.cleanup()

    def post(self, path="/api/status", body=b"{}", headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": f"127.0.0.1:{self.port}", "X-LP-Token": self.token, "Content-Type": "application/json"}
        h.update(headers or {})
        conn.request("POST", path, body, h)
        r = conn.getresponse()
        data = r.read()
        out = (r.status, dict(r.getheaders()), data)
        conn.close()
        return out

    def test_the_normal_call_works(self):
        status, headers, _ = self.post()
        self.assertEqual(200, status)
        self.assertEqual("no-referrer", headers["Referrer-Policy"])
        self.assertEqual("same-origin", headers["Cross-Origin-Resource-Policy"])

    def test_a_request_from_another_site_is_refused_even_with_the_token(self):
        self.assertEqual(403, self.post(headers={"Origin": "http://evil.example"})[0])
        self.assertEqual(403, self.post(headers={"Origin": f"http://127.0.0.1:{self.port + 1}"})[0])
        self.assertEqual(403, self.post(headers={"Origin": "null"})[0])
        self.assertEqual(200, self.post(headers={"Origin": f"http://127.0.0.1:{self.port}"})[0])      # the page itself
        self.assertEqual(200, self.post(headers={"Origin": f"http://localhost:{self.port}", "Host": f"localhost:{self.port}"})[0])

    def test_the_media_type_is_read_exactly(self):
        self.assertEqual(415, self.post(headers={"Content-Type": "text/plain; x=application/json"})[0])
        self.assertEqual(415, self.post(headers={"Content-Type": "text/plain"})[0])
        self.assertEqual(200, self.post(headers={"Content-Type": "Application/JSON; charset=utf-8"})[0])

    def test_a_body_nested_hundreds_of_thousands_deep_is_a_400(self):
        body = b'{"a":' + b"[" * 400000 + b"]" * 400000 + b"}"
        self.assertEqual(400, self.post(body=body)[0])
        self.assertEqual(200, self.post()[0])                                          # and the server carries on

    def test_the_text_false_is_not_a_yes(self):
        data = self.app.data_dir
        (data / "keepme.txt").write_text("x")
        status, _, raw = self.post("/api/self_uninstall", json.dumps({"confirm": "false", "remove_program": "false",
                                                                       "delete_created": "false", "keep_saves": "false"}).encode())
        self.assertEqual(200, status)
        self.assertNotIn("steps", json.loads(raw))                                     # only the plan was returned: nothing was done
        self.assertTrue((data / "keepme.txt").exists())
        status, _, raw = self.post("/api/game_uninstall", json.dumps({"id": "nope", "confirm": "no"}).encode())
        self.assertIn(status, (200, 400))
        self.assertNotIn("removed", raw.decode().lower())


if __name__ == "__main__":
    unittest.main()
