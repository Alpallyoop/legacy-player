# Legacy Player: current state

**Status:** Canonical record of where things stand. Update it with every audit, and never rewrite past entries
elsewhere: dated audits stay in `docs/audits/`.
**As of:** 2026-11-04, version 0.7.48 plus the unreleased changes in `CHANGELOG.md`
(`docs/audits/AUDIT_2026-11-01.md`; security audit `docs/audits/AUDIT_2026-11-04.md`).

## Works, with automated tests

| Area | State | Evidence |
|---|---|---|
| Library, covers, game details, PC games | Works | LP-LR-001 to 003 in `docs/REQUIREMENTS_TRACEABILITY.md` |
| Emulators: find, install from official releases, launch, overlay | Works; most default command lines not yet checked on Windows | LP-LR-010 to 012 |
| Controllers, saves, backups | Works; RetroArch bindings from real pads not checked | LP-LR-020, 030 |
| Lobby, rooms, invite codes, approval, waiting line | Works | LP-LR-040 |
| Matches: relay only, encrypted (RetroArch TCP; Dolphin NetPlay as UDP inside the tunnel) | Works on one computer in tests; not yet between two real networks | LP-LR-041; `tests/test_relay.py`, `tests/test_dolphin_relay.py`, `tests/test_launcher.py`, `tests/test_rendezvous.py` (a match through the meeting point) |
| Host address private: `LP3-` codes through a meeting point, home-network codes otherwise | Works in tests, including two real app instances through a real meeting point | LP-LR-042; `tests/test_rendezvous.py`, `tests/test_meeting_point_app.py`, `tests/test_friends_two_apps.py`, `tests/test_community_lobby.py` |
| Friends on the game server, end-to-end encrypted messages, moderation | Works | LP-LR-050 to 052 |
| TV mode | Works with keyboard and simulated pads; not checked with a real controller on Windows | LP-LR-060 |
| Consent: every action gated, versioned and undoable; address features retired | Works | LP-LR-070; `tests/test_consent.py` |
| Problem reports, self-update, uninstall, one data folder | Works; replacing the running exe not checked on Windows | LP-LR-071 to 092 |
| Research runtime (memory authority, state, events, replay, lockstep) | Partial: the live MEM1 validation run on Dolphin is next | `docs/WBS.md` (WBS 6), LP-FR rows |

Last full run: the whole suite under Python 3.13 on Linux with Playwright, with every test passing and only the
Windows-only tests skipped. See the audit for the exact counts.

## Open, in order

1. **A release that carries the built-in meeting point.** Since 2026-11-01 a meeting point runs on AWS Lightsail
   (us-east-1, static address, about USD 5 a month; it updates itself from the release branch every 30 minutes) and
   `PUBLIC_SERVER_CODE` names it. Players get it with the next release, or by running from source; older copies can
   paste the code under Settings > Your server > Meeting point code.
2. **Two real homes with real emulators.** On 2026-11-01 a player's computer (behind a home router) and a client on
   another network (a separate AWS server) met through the real meeting point with only an `LP3-` code: a
   RetroArch-style TCP match and a Dolphin-style UDP match each made 40 of 40 round trips through the relay (median
   about 20 ms). Still to do: real RetroArch and Dolphin, with real games, between two homes
   (`docs/MULTIPLAYER_TEST_PLAN.md`).
3. **Windows hardware.** Walk `docs/WINDOWS_CHECKLIST.md`: tray, firewall rule, window placement, self-update
   replacing the exe, and a real controller in TV mode.
4. **Constellation registry.** The registry entry, `docs/canonical/ECOSYSTEM_INTEGRATION.md` (owns: `UNCLASSIFIED`) and
   `project.contract.json` still need to follow ADR-0002. These files are managed by Constellation and must be changed
   from there.
5. **Code signing.** There is no certificate yet (`docs/CODE_SIGNING_POLICY.md`).

## Known limits, said plainly

- Whoever runs a meeting point or a server sees the addresses that connect to it. Nothing logs or stores them.
- Every match goes through the relay, which adds one hop of delay. The best results are between nearby players.
- PSP (PPSSPP ad hoc) and 3DS (Azahar rooms) are direct and can not be relayed, so they are for one home network only.
- An `LP3-` code is long (about 100 characters) because it carries the meeting point too. It is meant to be copied,
  not typed.
- An older app that offers a direct match can not publish it through a server of this version. Hosts should update.
- A meeting point holds at most 2,000 parked connections and carries at most 512 at once. Each player's server parks
  4, and one address may hold 16 connections. So behind one shared provider address (carrier-grade NAT), only about
  four home servers can park at the same meeting point.
- Friends who come through a meeting point have no address on the player's server. They share a slowed (never locked)
  budget for wrong keys and new names, and at most half the server's connections.
- Self-update checks that a download is intact, not who published it, until the maintainers list an update signing
  key in `launcher/version.py`. Signing is built and tested but needs that key (`docs/RELEASE.md`, "Update signing").
- The friends service can not read messages or server codes, but sees who is friends with whom, when messages are
  sent and how long they are.
- An old short `LP-` code without a key (made before 2026-11-04) is pinned by only 40 bits of its fingerprint; new
  codes carry 80. The player's own server is always pinned by 80 bits inside, end to end.
- Like the match tunnel before it, the socket bridge and the Dolphin datagram tunnel read from and write to one TLS
  socket from two threads at once. OpenSSL does not promise that is safe. No failure has been seen, but it has not been
  tested on Windows under load.
