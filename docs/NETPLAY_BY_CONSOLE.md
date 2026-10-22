# Netplay by console: what works, what does not, and how

| Console | How you play together | Address privacy | Status |
|---|---|---|---|
| NES, SNES, GB/GBC/GBA, Genesis, Atari | RetroArch netplay, launched by Legacy Player | Relay only: nobody sees an address | Verified: 4 players, 60 s, no desync (RetroArch 1.18) |
| PlayStation | RetroArch netplay, PCSX-ReARMed core (or SwanStation) | Relay only | Experimental: same BIOS everywhere; large save states |
| Nintendo 64 | RetroArch netplay, Mupen64Plus-Next core | Relay only | Experimental: least stable, expect desyncs |
| Nintendo DS | RetroArch netplay, melonDS core | Relay only | Experimental: one game in lockstep; no local-wireless |
| GameCube, Wii | Dolphin NetPlay, guided by Legacy Player | Relay only: each Dolphin connects to its own computer (`127.0.0.1`) and Legacy Player carries the UDP datagrams through the relay, encrypted | Guided; tested with a stand-in for Dolphin, not yet with real Dolphin over two networks |
| PSP | PPSSPP ad hoc: host turns on *Enable built-in PRO ad hoc server*, everyone sets *Change PRO ad hoc server IP* to the host; each player needs a unique MAC in PPSSPP settings | Direct only, so addresses are exchanged; the relay can not carry it. Use it on a home network | Manual; Legacy Player opens the game and shows these steps |
| PlayStation 2 | None. PCSX2 has no netplay | — | Not possible today |
| Xbox | None (System Link on one home network only) | — | Not possible |
| Xbox 360 | None | — | Not possible |
| PlayStation 3 | None through Legacy Player; some games' own online works through RPCN inside RPCS3 | — | Not possible here |
| 3DS | None through Legacy Player; Azahar local-wireless rooms exist | — | Not possible here |

How the relay keeps addresses private: the host and every guest connect *out* to the lobby
server; the server pairs them and copies bytes. The bytes are the match's TLS-PSK tunnel, so
the server cannot read the game: the match key is not sent through it, each guest works it out from the host's *public* key (X25519), so a passive or logging server operator learns nothing. (A server operator who actively swaps keys could still sit in the middle; run your own server, or play with people you trust, if that matters to you.) Verified with real RetroArch: host + 2 guests, about 25 ms
extra ping on loopback.

There is no direct mode any more. Direct matches, hole punching and Dolphin's traversal server all exchanged
addresses, so they were removed (`docs/canonical/SPEC.md`, "Addresses"). The server itself refuses a direct address or
a Dolphin host code, so an older app can not publish one through it.

Dolphin through the relay: the host opens NetPlay > Host with *Direct Connection* and port 2626 (on its own computer;
nothing is opened on the router); each guest enters the address and port the app shows (`127.0.0.1` and a local port).
Datagrams travel inside the match's TLS-PSK tunnel, each with a 2-byte length in front (`adapters/dolphin/udp_relay.py`).
Expect a little more delay than a direct link, since the relay uses TCP.

## Known limits

- **RetroArch and Dolphin still listen on their port on every network interface.** Neither has a bind option.
  Guests only ever reach the match through the relay, and Legacy Player never opens these ports on the router, so
  keep them (55435 and 2626 by default) closed at your router and firewall.
- **Step guides** for PSP, 3DS and PS3 are shown in the room on the Servers page when those games are in it (the
  emulators run these modes themselves; Legacy Player cannot start them).
- **Pad profiles** (identify and map) are applied to RetroArch only. Other emulators keep their own controller
  settings; set the pad inside the emulator once.
- **Waiting while you play:** you can play any game in any emulator while you hold a place in line; when a seat
  opens you get a notice, and *It's my turn: switch* closes your current game politely (the emulator saves like
  clicking X) and joins. A background pre-loaded spectator was tried with real RetroArch: it can connect without
  taking a seat (netplay_start_as_spectator), but RetroArch cannot be switched from watching to playing without a
  keypress inside its window, so a fresh launch at switch time is used instead.
