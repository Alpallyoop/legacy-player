import ipaddress
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from unittest import mock

from launcher import portmap


def allow_test_loopback(case):
    """The fake routers below listen on 127.0.0.1, which the real check refuses; let exactly that address through."""
    real = portmap._allow_router_ip
    p = mock.patch.object(portmap, "_allow_router_ip", lambda ip: ip == ipaddress.ip_address("127.0.0.1") or real(ip))
    p.start()
    case.addCleanup(p.stop)

DESC = """<?xml version="1.0"?><root xmlns="urn:schemas-upnp-org:device-1-0"><device><serviceList><service>
<serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType><controlURL>/ctl</controlURL></service></serviceList></device></root>"""


def router(outside, refuse_forever=False):
    seen = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(DESC.encode())

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            action = self.headers["SOAPAction"].strip('"').split("#")[1]
            seen.append((action, body))
            if action == "AddPortMapping" and refuse_forever and "<NewLeaseDuration>0<" in body:
                self.send_response(500); self.end_headers()
                self.wfile.write(b"<errorCode>725</errorCode>"); return
            self.send_response(200); self.end_headers()
            if action == "GetExternalIPAddress":
                self.wfile.write(f"<NewExternalIPAddress>{outside}</NewExternalIPAddress>".encode())
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen, f"http://127.0.0.1:{srv.server_port}/desc.xml"


class PortMapTests(unittest.TestCase):
    def setUp(self):
        allow_test_loopback(self)

    def test_opens_and_reports_public_address(self):
        srv, seen, loc = router("93.184.216.34")
        self.addCleanup(srv.shutdown)
        r = portmap.open_port(8765, 2, [loc], "192.168.1.5")
        self.assertEqual("mapped", r["state"])
        self.assertEqual("93.184.216.34", r["external_ip"])
        add = [b for a, b in seen if a == "AddPortMapping"][0]
        self.assertIn("<NewInternalClient>192.168.1.5<", add)
        self.assertIn("<NewExternalPort>8765<", add)

    def test_shared_provider_address_is_not_reachable_and_mapping_removed(self):
        srv, seen, loc = router("100.72.1.9")
        self.addCleanup(srv.shutdown)
        r = portmap.open_port(8765, 2, [loc], "192.168.1.5")
        self.assertEqual("not_reachable", r["state"])
        self.assertEqual("cgnat", r["kind"])
        self.assertIn("DeletePortMapping", [a for a, _ in seen])

    def test_router_that_refuses_forever_gets_a_lease(self):
        srv, seen, loc = router("93.184.216.34", refuse_forever=True)
        self.addCleanup(srv.shutdown)
        self.assertEqual("mapped", portmap.open_port(8765, 2, [loc], "192.168.1.5")["state"])

    def test_no_router(self):
        r = portmap.open_port(8765, 1, [], "192.168.1.5")
        self.assertEqual("no_router", r["state"])

    def test_kinds(self):
        self.assertEqual("cgnat", portmap.address_kind("100.64.3.3"))
        self.assertEqual("private", portmap.address_kind("192.168.0.9"))
        self.assertEqual("public", portmap.address_kind("8.8.8.8"))


def redirecting_router(desc_redirect=True, soap_redirect=False, desc_body=None, big=False):
    hits = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            hits.append(("GET", self.path))
            if desc_redirect and self.path == "/desc.xml":
                self.send_response(302); self.send_header("Location", "http://127.0.0.1:%d/elsewhere" % self.server.server_port)
                self.end_headers(); return
            self.send_response(200); self.end_headers()
            body = desc_body if desc_body is not None else DESC.encode()
            self.wfile.write(body + (b" " * (portmap.DESCRIPTION_LIMIT + 10) if big else b""))

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            hits.append(("POST", self.path))
            if soap_redirect and self.path == "/ctl":
                self.send_response(307); self.send_header("Location", "http://127.0.0.1:%d/other" % self.server.server_port)
                self.end_headers(); return
            self.send_response(200); self.end_headers()
            self.wfile.write(b"<NewExternalIPAddress>93.184.216.34</NewExternalIPAddress>")
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, hits, f"http://127.0.0.1:{srv.server_port}/desc.xml"


class PortMapHardeningTests(unittest.TestCase):
    """Audit 2026-11-04: a device on the network must not steer UPnP requests elsewhere."""

    def setUp(self):
        allow_test_loopback(self)

    def test_description_redirect_is_not_followed(self):
        srv, hits, loc = redirecting_router()
        self.addCleanup(srv.shutdown)
        with self.assertRaises(portmap.PortMapError):
            portmap.Gateway(loc, 2)
        self.assertEqual([("GET", "/desc.xml")], hits)

    def test_soap_redirect_is_not_followed(self):
        srv, hits, loc = redirecting_router(desc_redirect=False, soap_redirect=True)
        self.addCleanup(srv.shutdown)
        gw = portmap.Gateway(loc, 2)
        with self.assertRaises(portmap.PortMapError) as cm:
            gw.external_ip()
        self.assertIn("somewhere else", str(cm.exception))
        self.assertNotIn(("POST", "/other"), hits)

    def test_oversized_description_is_refused(self):
        srv, _, loc = redirecting_router(desc_redirect=False, big=True)
        self.addCleanup(srv.shutdown)
        with self.assertRaises(portmap.PortMapError):
            portmap.Gateway(loc, 2)

    def test_description_with_a_dtd_is_refused(self):
        for body in (b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "x">]><root>&a;</root>',
                     b'<!DOCTYPE root SYSTEM "http://192.168.1.9/x.dtd"><root/>'):
            srv, _, loc = redirecting_router(desc_redirect=False, desc_body=body)
            self.addCleanup(srv.shutdown)
            with self.assertRaises(portmap.PortMapError):
                portmap.Gateway(loc, 2)

    def test_router_must_be_a_private_address_on_this_network(self):
        with mock.patch.object(portmap, "_local_ipv4_addresses", return_value=["192.168.1.5"]):
            ok = portmap.Gateway._local_http
            self.assertTrue(ok("http://192.168.1.1:5000/desc.xml"))
            for bad in ("http://127.0.0.2:80/x", "http://localhost/x", "http://0.0.0.0/x", "http://239.255.255.250/x",
                        "http://169.254.1.1/x", "http://192.168.2.1/x", "http://10.0.0.1/x", "http://8.8.8.8/x",
                        "http://100.64.0.1/x", "http://192.168.1.5/x", "https://192.168.1.1/x", "http://[fe80::1]/x",
                        "http://u:p@192.168.1.1/x", "file:///etc/passwd"):
                self.assertFalse(ok(bad), bad)
        with mock.patch.object(portmap, "_local_ipv4_addresses", return_value=["169.254.7.7"]):
            self.assertTrue(portmap.Gateway._local_http("http://169.254.1.1/x"))
        with mock.patch.object(portmap, "_local_ipv4_addresses", return_value=[]):
            self.assertFalse(portmap.Gateway._local_http("http://192.168.1.1/x"))

    def test_real_check_refuses_loopback_without_the_test_hook(self):
        mock.patch.stopall()
        self.assertFalse(portmap._allow_router_ip(ipaddress.ip_address("127.0.0.1")))

    def test_requests_never_use_an_http_proxy(self):
        handlers = [type(h).__name__ for h in portmap._OPENER.handlers]
        self.assertIn("_NoRedirect", handlers)
        proxy = [h for h in portmap._OPENER.handlers if isinstance(h, portmap.urllib.request.ProxyHandler)]
        self.assertFalse([h for h in proxy if h.proxies])            # ProxyHandler({}) also keeps the default (env) one out
        with mock.patch.dict("os.environ", {"http_proxy": "http://203.0.113.9:3128", "HTTP_PROXY": "http://203.0.113.9:3128"}):
            fresh = portmap.urllib.request.build_opener(portmap.urllib.request.ProxyHandler({}), portmap._NoRedirect())
            self.assertFalse([h for h in fresh.handlers if isinstance(h, portmap.urllib.request.ProxyHandler) and h.proxies])


if __name__ == "__main__":
    unittest.main()
