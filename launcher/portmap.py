"""Open the server's port on the home router by itself (UPnP), so a friend only needs the server code.

Most home routers answer a UPnP request from a program on the network: "please send TCP port N to this computer".
This module asks, reads back the router's public address, and removes the mapping again when the server stops.
It talks only to the router on the local network (SSDP multicast, then the router's own address); nothing leaves
the house. Routers that have UPnP turned off, and providers that share one public address between customers
(carrier-grade NAT, which includes most phone hotspots), cannot be opened this way; the result says which it was.
"""
from __future__ import annotations

import ipaddress
import pyexpat
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

SSDP_ADDR = ("239.255.255.250", 1900)
SEARCH_TARGETS = ("urn:schemas-upnp-org:device:InternetGatewayDevice:2", "urn:schemas-upnp-org:device:InternetGatewayDevice:1")
WAN_SERVICES = ("urn:schemas-upnp-org:service:WANIPConnection:2", "urn:schemas-upnp-org:service:WANIPConnection:1",
                "urn:schemas-upnp-org:service:WANPPPConnection:1")
DESCRIPTION = "Legacy Player server"


class PortMapError(Exception):
    pass


def address_kind(ip: str) -> str:
    """public | cgnat | private | unknown. A router whose own outside address is not public cannot be reached from outside."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return "unknown"
    if a in ipaddress.ip_network("100.64.0.0/10"):
        return "cgnat"
    if a.is_private or a.is_loopback or a.is_link_local or a.is_unspecified:
        return "private"
    return "public"


def _local_ipv4_addresses() -> list[str]:
    """Every IPv4 address of this computer. A search sent only on the default route misses a router that sits behind
    another adapter (a VPN, a virtual machine switch and WSL each add one), so the search is sent from each."""
    found: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in found and not ip.startswith("127."):
                found.append(ip)
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("192.0.2.1", 9))
            ip = probe.getsockname()[0]
            if ip not in found and not ip.startswith("127."):
                found.insert(0, ip)
        finally:
            probe.close()
    except OSError:
        pass
    return found


def _search_from(source: str | None, timeout: float, found: list[str]) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.settimeout(0.5)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        if source:
            try:
                sock.bind((source, 0))
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(source))
            except OSError:
                return
        for target in SEARCH_TARGETS + ("upnp:rootdevice",):
            msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 2\r\nST: %s\r\n\r\n" % target).encode()
            try:
                sock.sendto(msg, SSDP_ADDR)
            except OSError:
                continue
        import time
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            match = re.search(r"^location:\s*(\S+)", data.decode("latin-1"), re.I | re.M)
            if match and match.group(1) not in found:
                found.append(match.group(1))
    finally:
        sock.close()


def _find_locations(timeout: float) -> list[str]:
    found: list[str] = []
    sources = _local_ipv4_addresses() or [None]
    per = max(2.0, timeout / max(1, len(sources)))
    for source in sources:
        _search_from(source, per, found)
        if found:
            break
    if not found:                                    # last try the old way, on whatever the system picks
        _search_from(None, per, found)
    return found


def _local_address_towards(host: str) -> str:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((host, 9))
        return probe.getsockname()[0]
    finally:
        probe.close()


DESCRIPTION_LIMIT = 200_000                 # bytes; a router's description is a few kB
SOAP_LIMIT = 100_000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A device on the network must not be able to send our request somewhere else (the internet, or this computer's
    own services on 127.0.0.1): a redirect is treated as a failure, for the description and for every SOAP call."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# No proxy either: these requests are for the router on this network only and must not go out through HTTP(S)_PROXY.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _read_capped(r, limit: int) -> bytes:
    data = r.read(limit + 1)
    if len(data) > limit:
        raise PortMapError("The router's answer was too large.")
    return data


def _refuse_dtd(*_a) -> None:
    raise PortMapError("The router's answer declared a DTD or entities, so I stopped.")


def _parse_xml(text: str) -> ET.Element:
    """Parse a router's XML, refusing any DOCTYPE or entity declaration (checked by expat itself, whatever the encoding)."""
    check = pyexpat.ParserCreate()
    check.StartDoctypeDeclHandler = _refuse_dtd
    check.EntityDeclHandler = _refuse_dtd
    check.UnparsedEntityDeclHandler = _refuse_dtd
    check.ExternalEntityRefHandler = lambda *a: _refuse_dtd()
    try:
        check.Parse(text, True)
        return ET.fromstring(text)
    except (pyexpat.ExpatError, ET.ParseError) as exc:
        raise PortMapError("The router's description could not be read.") from exc


def _allow_router_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """A router is a private LAN address on one of this computer's own networks: never loopback, unspecified, multicast,
    CGNAT or a public address; link-local only when this computer is itself on that link-local network. "On this
    network" is the same /24 as one of this computer's IPv4 addresses (home routers hand out /24s)."""
    if ip.version != 4 or ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        return False
    rfc1918 = any(ip in ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
    if not (rfc1918 or ip.is_link_local):
        return False
    for mine in _local_ipv4_addresses():
        try:
            own = ipaddress.ip_address(mine)
        except ValueError:
            continue
        if ip == own:
            continue                     # this computer is not the router
        net = ipaddress.ip_network(f"{mine}/16" if ip.is_link_local else f"{mine}/24", strict=False)
        if ip.is_link_local == own.is_link_local and ip in net:
            return True
    return False


class Gateway:
    """One UPnP router."""

    def __init__(self, location: str, timeout: float = 3.0) -> None:
        self.location, self.timeout = location, timeout
        self.control = ""
        self.service = ""
        self._describe()

    @staticmethod
    def _local_http(url: str) -> bool:
        """Only plain http to a router address on this network: a device answering the search can not send us to the
        internet, or to a service on this computer."""
        try:
            parts = urllib.parse.urlparse(url)
            port = parts.port
        except ValueError:
            return False
        if parts.scheme != "http" or not parts.hostname or parts.username or parts.password or port == 0:
            return False
        try:
            ip = ipaddress.ip_address(parts.hostname)
        except ValueError:
            return False
        return _allow_router_ip(ip)

    def _describe(self) -> None:
        if not self._local_http(self.location):
            raise PortMapError("The router's address is not on this network.")
        try:
            with _OPENER.open(self.location, timeout=self.timeout) as r:
                text = _read_capped(r, DESCRIPTION_LIMIT).decode("utf-8", "replace")
        except (OSError, urllib.error.URLError) as exc:          # a redirect arrives here as an HTTPError
            raise PortMapError("The router did not describe itself.") from exc
        text = re.sub(r'\sxmlns="[^"]+"', "", text, count=1)
        root = _parse_xml(text)
        for svc in root.iter("service"):
            kind = (svc.findtext("serviceType") or "").strip()
            if kind in WAN_SERVICES:
                url = (svc.findtext("controlURL") or "").strip()
                if url:
                    control = urllib.parse.urljoin(self.location, url)
                    if not self._local_http(control) or urllib.parse.urlparse(control).hostname != urllib.parse.urlparse(self.location).hostname:
                        raise PortMapError("The router pointed somewhere else, so I stopped.")
                    self.service, self.control = kind, control
                    return
        raise PortMapError("This router does not offer port mapping.")

    def _soap(self, action: str, args: dict) -> str:
        body = "".join(f"<{k}>{v}</{k}>" for k, v in args.items())
        envelope = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
                    f'<u:{action} xmlns:u="{self.service}">{body}</u:{action}></s:Body></s:Envelope>').encode()
        req = urllib.request.Request(self.control, envelope, {"Content-Type": 'text/xml; charset="utf-8"',
                                                              "SOAPAction": f'"{self.service}#{action}"'})
        try:
            with _OPENER.open(req, timeout=self.timeout) as r:
                return _read_capped(r, SOAP_LIMIT).decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:                    # includes a refused redirect (3xx)
            if 300 <= exc.code < 400:
                raise PortMapError("The router tried to send the request somewhere else, so I stopped.") from exc
            detail = exc.read(4000).decode("utf-8", "replace")
            code = re.search(r"<errorCode>(\d+)</errorCode>", detail)
            raise PortMapError("code " + (code.group(1) if code else str(exc.code))) from exc
        except (OSError, urllib.error.URLError) as exc:
            raise PortMapError("The router did not answer.") from exc

    def external_ip(self) -> str:
        text = self._soap("GetExternalIPAddress", {})
        match = re.search(r"<NewExternalIPAddress>([^<]*)</NewExternalIPAddress>", text)
        return match.group(1).strip() if match else ""

    def add(self, port: int, internal_ip: str, lease: int = 0) -> None:
        self._soap("AddPortMapping", {"NewRemoteHost": "", "NewExternalPort": port, "NewProtocol": "TCP", "NewInternalPort": port,
                                      "NewInternalClient": internal_ip, "NewEnabled": 1, "NewPortMappingDescription": DESCRIPTION,
                                      "NewLeaseDuration": lease})

    def delete(self, port: int) -> None:
        self._soap("DeletePortMapping", {"NewRemoteHost": "", "NewExternalPort": port, "NewProtocol": "TCP"})


LEASE_SECONDS = 7200
RENEW_SECONDS = 3000


def renew_port(port: int, location: str, local_ip: str, timeout: float = 4.0) -> bool:
    """Extend the router mapping before its lease runs out."""
    try:
        Gateway(location, timeout).add(port, local_ip, LEASE_SECONDS)
        return True
    except (PortMapError, OSError):
        return False


def open_port(port: int, timeout: float = 4.0, locations: list[str] | None = None, local_ip: str | None = None) -> dict:
    """Ask the router to forward `port`. Never raises. state: mapped | not_reachable | no_router | refused."""
    last = "No router answered. UPnP may be switched off in the router's settings."
    for location in (locations if locations is not None else _find_locations(timeout)):
        try:
            gw = Gateway(location, timeout)
            host = urllib.parse.urlparse(location).hostname or ""
            mine = local_ip or _local_address_towards(host)
            try:
                gw.add(port, mine, LEASE_SECONDS)      # expires by itself if the app crashes; the app renews it while running
            except PortMapError:
                gw.add(port, mine, 0)                  # some routers refuse timed leases; the app closes it itself then
            outside = gw.external_ip()
        except (PortMapError, OSError) as exc:
            last = str(exc)
            continue
        kind = address_kind(outside)
        if kind != "public":
            try:
                gw.delete(port)
            except PortMapError:
                pass
            return {"state": "not_reachable", "external_ip": outside, "kind": kind, "location": location,
                    "message": "Your router's outside address is shared with other customers (or is not public), so people outside "
                               "your home cannot connect straight in. Friends can still join over a VPN, or through a relay server."}
        return {"state": "mapped", "external_ip": outside, "kind": "public", "location": location, "local_ip": mine, "port": port,
                "message": "Port opened on your router automatically. Friends can use your server code."}
    return {"state": "refused" if last.startswith("code") else "no_router", "external_ip": "", "kind": "unknown",
            "message": "Could not open the port on your router automatically (" + last + "). Turn on UPnP in the router, "
                       "or friends can use a VPN."}


def close_port(port: int, location: str, timeout: float = 4.0) -> bool:
    try:
        Gateway(location, timeout).delete(port)
        return True
    except (PortMapError, OSError):
        return False
