# Cross-network multiplayer test plan

Goal: one player on the home network, one on a phone hotspot (a different network), on another computer.

## The one thing to know first
A phone hotspot is usually behind carrier-grade NAT: nothing outside can connect *in* to it. That is fine as long as the
hotspot computer only connects *out*. So:

- **Friends reach the host's server through a meeting point** (`docs/HOSTING_PUBLIC_SERVER.md`). The host's server
  connects *out* to it, so no port is forwarded and either side may be on the hotspot.
- **Every match goes through the relay.** Neither side ever sees the other's address.

## Setup (what the player does)
0. Run a meeting point on a machine with a public address (`deploy/README.md`) and put its code in Settings > Your
   server > "Meeting point code" on the host (or build it into the release as `PUBLIC_SERVER_CODE`).
1. Home computer: Servers page, leave "Let friends connect" ticked, press Start. Allow "Meeting point for friends outside
   my home" when asked. How friends reach me should say the meeting point works.
2. Share the server code (`LP3-...`; it holds no address of the host). The friend pastes it into Connect to a server.
3. Both: Settings > Privacy > Problem reports > "Ask me each time", so a failure produces a report you can read.

No router or firewall change is needed through a meeting point. Without one, only players on the host's home network
can join (the code then holds a home-network address only).

## What to check, in order
1. Network page on each side: address kind (home / hotspot-style / CGNAT) and the connectivity test result.
2. Hotspot side can see the server and the room list.
3. Create a room on one side, join from the other; players count shows 2 on both.
4. Start a game (RetroArch, and Dolphin for GameCube); note the ping shown in the title bar.
5. Check that no screen, log, report or code on either side shows the other's address.
6. Leave and rejoin once; stop the server and see that the client says so clearly.

## When something fails
Choose "See exactly what would be sent", then send (or copy) the report. Until the receiver is hosted
(`server/report_receiver.py` behind https, address in `launcher/version.py` `REPORT_URL`), use "Copy the newest report"
in Settings and paste it to the maintainers.
