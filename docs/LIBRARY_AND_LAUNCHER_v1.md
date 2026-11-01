# Library and Launcher v1

Status: implemented under Proposal 0002, which is still "Proposed (not approved)" (see
`docs/proposals/2026-10-12-launcher-approval-and-canonical-docs.md`). Standard library only.

This is the original v1 design note, kept up to date on facts (paths, page names); the newest behaviour is in
`README.md` and the in-app Help page.

## Run it

```
python -m launcher --games "P:\Vimm"                    # use YOUR games folder; opens http://127.0.0.1:8780
python -m launcher                                       # or start empty and add the folder in the app
python -m server.cli start --detach                      # multiplayer server (optional)
```

User data (favorites, settings, history, controller overrides, save backups, downloaded emulators, logs) lives in one
folder: `LegacyPlayerData` inside the Legacy Player folder for the Windows app, or `data` in the checkout when run from
source (`--data-dir` or Settings > Where Legacy Player keeps its files to change; `launcher/datadir.py` has the full
rule). Version 0.7.44 and older used `~/.legacy-player`; the app offers once to move those files. Game folders are only
ever read.

## What it does

| Area | Behavior |
|---|---|
| Scanner | Walks the chosen folders and classifies files by extension, using the folder name for shared types (.iso, .bin, .zip, .7z). Skips `Emulators`, `ZZZ-*`, `saves`, `BIOS`. A `.bin` beside a `.cue` is collapsed to the `.cue`. Never opens, hashes, copies or modifies a file (tested). |
| Library | Console shelf with counts, search, favorites, sort (A-Z, recent, size), detail drawer. |
| Identity | `compat_id` = console + normalized title + region, identical on every player's machine; used to check that everyone in a room has the same game. |
| Emulators | Finds known emulators under the games folder (3 levels deep) and on PATH, or uses a path you set. Launch uses an argument list, never a shell, and only for a game already in the library. Default command lines are common documented ones and are unverified until proven on your machine. |
| Controllers | Standard-gamepad layout mapped per console (17 layouts in `launcher/controllers.py` for 18 consoles: Game Boy Color shares the Game Boy layout; PC games use the Xbox 360 one). Editable, resettable, with live pad test in the browser. Applying a mapping inside each emulator is adapter work (Dolphin first). |
| Saves | Finds save files by game name in the emulator save folder (cartridge consoles default to the game's own folder), timestamped backups, restore backs up current saves first. |
| Settings | Schema-driven with plain-language help for every option. |
| Servers (was "Play Together") | Host or join rooms by invite code, approve/decline requests, remove players with a reason, check everyone matches, ready up, live activity feed and toasts for joins, leaves, kicks, disconnects and server restarts. |

## Honest limits

- Match launch uses RetroArch's own netplay (see below), so it covers NES, SNES, Game Boy,
  Game Boy Color, GBA, Genesis and Atari only. GameCube (Dolphin, Mario Party 4) still goes
  through the lockstep adapter work; other consoles have no match launcher yet.
- Archives (.7z, most .zip) are listed but must be extracted by you before launching.
- Memory-card consoles share one card file, so per-game save backup needs a save folder set.
- Multiplayer feasibility labels per console are guidance, not a compatibility promise.

## Security model of the UI

Loopback only; every API call needs a per-run token embedded in the page; `Host` header and
`Content-Type: application/json` are enforced (blocks DNS rebinding and cross-site forms);
the UI builds the DOM with text nodes so file names cannot inject markup; errors never leak
tracebacks.

## Starting a match (Phase 3a: RetroArch native netplay)

`adapters/retroarch/netplay.py` is a *launch* adapter: it starts RetroArch in host or
client mode and leaves frame sync to RetroArch and the libretro core. It does not implement
the lockstep `ControllerAdapter`. Legacy Player supplies the room, invite code, compatibility
check and the relay.

Flow: host presses "Check everyone matches", then "Launch match (host)". The launcher starts
RetroArch with `-L <core> <game> --host --port <port> --nick <name>`, parks relay connections
at the server and publishes a relay endpoint with the match key (`set_endpoint` kind `relay`, `psk`).
Guests are notified, press "Join match", and the launcher starts a local tunnel and
`... --connect 127.0.0.1 --port <tunnel port>`. No address is ever published: the server accepts
only relay endpoints.

Requirements and honest limits:
- RetroArch plus a libretro core for the console in `<retroarch folder>/cores` (the UI says
  exactly what is missing). Everyone needs the same core and the same game file version.
- The RetroArch flags were verified against a real RetroArch 1.18 (host + 3 guests, 60 s, no desync).
- Every match is wrapped in a TLS-PSK tunnel and relayed through the lobby server, so players never learn each other's address. Dolphin NetPlay too: its UDP datagrams travel inside the tunnel (`adapters/dolphin/udp_relay.py`).

## Dolphin (GameCube and Wii) guided NetPlay

Dolphin has no command-line option to start or join NetPlay, so `adapters/dolphin/netplay_guide.py`
does not drive it. "Open Dolphin" opens Dolphin's normal window without starting the game (NetPlay
refuses while a game runs) and shows ordered steps, through the relay only:
- **Host:** NetPlay > Host, *Direct Connection*, port 2626, on its own computer. The app parks relay
  connections and gives each guest its own local UDP socket towards the host's Dolphin.
- **Guest:** NetPlay > Connect, *Direct Connection*, address `127.0.0.1` and the local port the app
  shows. The app carries the datagrams to the host through the relay.
Dolphin's traversal server and host codes are not used (they show addresses); the server refuses
`set_endpoint` kind `code` and `direct`.

Everyone needs the same Dolphin version, the same game file (region and revision) and the same
settings. This guided path is separate from the repository's lockstep Dolphin/DSU work for
Mario Party 4, which is not changed.

## Setup page

`Setup` checks RetroArch, one core per supported console, and Dolphin.
- **Windows:** can download the official stable RetroArch package (`RetroArch.7z`, unpacked with
  7-Zip or the `tar` that ships with Windows) and the missing cores into `emulators/retroarch` inside the data folder.
- **Linux:** downloads missing cores; RetroArch itself comes from your package manager or Flatpak
  (the page shows the command). **macOS:** guidance only.
- **Dolphin:** checked and linked to its official download page, not auto-installed.
- Downloads: official libretro build server only, https, redirects to other hosts refused, size caps,
  path-escape checks. The server publishes no checksums, so integrity rests on TLS to that host.
- The installer was tested against a local fake server. It could not reach the real server from the
  development sandbox, so the first real download happens on your machine.

## Controllers (any pad)

The **Controllers** page (Configure > Controllers) lists every pad the browser can see (Xbox, PlayStation, Switch Pro, 8BitDo, generic USB pads). Press a button on a pad to make it appear.

* **Identify** shows name, vendor:product, button and axis counts, and rumbles the pad if it can.
* **Map buttons** walks through 17 standard controls ("press the button for ..."). Buttons and axis directions are both accepted, so odd pads and hat switches work. Skip, Back and Cancel are available. The profile is saved per pad.
* **Player 1-4** assigns a pad to a player slot.
* Two layers: your pad profile (raw input to standard control) and the console layout (standard control to console button).

What is applied outside this app: for **RetroArch**, pads in the browser's standard layout (XInput style) get their bindings written to a per-console config passed with `--appendconfig`. Other pads, and all other emulators, keep their own controller settings; set those once inside the emulator. Windows controller input for RetroArch bindings has not been verified on a real Windows machine; the config flag itself was verified against RetroArch 1.18.

## Save folders

The **Saves** page (Configure > Saves and backups) sets one root folder (default: inside the Legacy Player data folder). RetroArch consoles get `<root>/<console>/saves` and `<root>/<console>/states`, passed with `--appendconfig` (`savefile_directory`, `savestate_directory`, no per-core subfolders). Verified against RetroArch 1.18: the folders are honored. Other emulators keep their own folders; the page shows where each usually keeps saves and lets you point backups at any folder. Backups remain timestamped copies and restoring backs up current files first.

## Encrypted matches

RetroArch matches run through a TLS 1.2 pre-shared-key tunnel (Python 3.13+, built into the downloadable app). The host shares a random key through the room; guests connect to a local tunnel port. A real RetroArch host and guest were connected through it (player 2 joined, ping about 30 ms). Every match uses it, Dolphin included (its UDP datagrams travel inside the tunnel); without TLS-PSK (an older Python) a match is refused, never downgraded. Limits: the lobby itself is only encrypted when the server uses TLS (always when it is shared); RetroArch and Dolphin still listen on their port, so keep it closed at the firewall.

## Downloadable app (.exe)

`build_exe.bat` (Windows, Python 3.13+) builds `dist\LegacyPlayer.exe`: one file, no Python needed to run it. It opens its own app-style window with Edge or Chrome, quits when the window closes, runs the multiplayer server for you (Start on the Servers page) and keeps data in the data folder described above. Releases are built by `.github/workflows/release.yml` (see `docs/RELEASE.md`). The PyInstaller packaging and the packaged server start/stop were verified on Linux; the owner has built `dist\\LegacyPlayer.exe` on Windows and opened it (Azahar launched from it). A full Windows smoke of every tab is still to do.

## Full rooms: waiting line and priority

The host picks a player limit (2 to 4) when hosting and can change it later. When the room is full, or others are already waiting, new people are not turned away: they join a **waiting line**.

* Everyone waiting sees their place ("You are number 2 in line"), and the host sees the list in the room.
* The line is first come, first served. **Priority** goes first: the host can give or remove priority per person, or create a **priority invite code**; anyone who joins with it queues ahead of normal people.
* When a spot frees (someone leaves or is removed, or the limit is raised) the next person is let in automatically, or sent to the host for approval if the room asks to approve everyone. The host can also remove someone from the line.
* Waiters must keep the page open. A place is dropped after about a minute without a check-in so a closed laptop cannot hold a spot. The line survives a server restart.
* Server operations: `set_priority`, `list_waiting`, `set_capacity`, `cancel_wait`; `create` accepts `max_players`, `invite` accepts `priority`.

## Engines, BIOS and TV mode (Phase 4, first slice)

See `docs/proposals/0003_OWNED_EMULATOR_SHELL.md`. In short: the **Engines** page (Configure > Engines) finds emulators already on the computer (Program Files, user folders, your emulator folders) when you press *Scan this computer*, fetches missing ones from each project's official GitHub releases when you press *Get* (only with the *Internet downloads and updates* permission, default off), and shows which BIOS files you need and where your own dumps are. BIOS files are never downloaded. **TV mode** (F11; a start-page choice, Home is the default) is the full-screen, controller-first home; the older Console mode, a big-tile view of the library, was merged into it in 0.7.47 (see `README.md` and `docs/USER_GUIDE.md`). Load numbers are in `docs/STRESS_TEST_RESULTS.md`.

## Open rooms, waiting while you play, and your shared server (Phase 4, second slice)

* **Open rooms**: tick *Open room* when hosting (optionally name it). Anyone on the server sees it under *Open rooms on this server* with the game, region, players/limit and line length, never who is inside. *Join* walks in; *Wait in line* queues you in the background so you can keep playing or hosting; you get a notice when your seat is ready and press *Switch to it*. Hosts can toggle open/private live.
* **Seats free themselves**: a player who stops talking to the server is flagged after 45 s and removed after about 2 minutes so the line moves. Leaving a RetroArch/Dolphin match no longer ends it for everyone (lockstep matches still stop, as they must).
* **Your server, shared safely**: *Let friends connect* starts the server with TLS using a certificate the app makes itself (no OpenSSL needed). With a meeting point the server listens on this computer only and the `LP3-` server code holds no address of it; friends' apps pin the certificate fingerprint in the code and refuse a server that does not match. Plaintext internet hosting is not offered. Limits (players per room, rooms, line length) are in Settings > Your server.
* **Who sees what**: other players see `Name#tag` (the tag comes from the server) and nothing else; the server sees your IP like any website does; matches always go through the server relay, so other players never see your address; there is no direct mode. One caveat: RetroArch and Dolphin still listen on their port on every network interface (no bind option), so do not forward those ports at your router.

### Server operations (wire protocol, newline JSON)

create, join (invite code, join code, or open room by session id), validate, ready, input, poll, checkpoint, complete, status, join_status, decide_join, invite (priority flag), revoke_invites, kick, leave, heartbeat, set_priority, list_waiting, cancel_wait, browse, set_open, set_capacity, set_endpoint (kind relay only, with psk; direct and code are refused), get_endpoint, relay (first line of a connection that becomes a byte pipe), punch (refused: hole punching is switched off), rv_park / rv_join (first line of a connection to a meeting point: `server/rendezvous.py`), events; admin (loopback + token, never through a meeting point): admin_status, admin_shutdown, admin_rotate_key (also a fresh meeting-point token), admin_meet_status.

## Your turn: switching from what you were playing

While you wait in line you can play anything from the library. When your seat is ready the app
says so; *It's my turn: switch* asks whether to close the game you are in (the emulator gets a
normal close request, the same as clicking its X, so it writes saves as usual), leaves any
room you were in, takes the seat, and joins the match at once if the host has launched.



## Direct connections (removed)

Hole punching and direct matches were removed on 2026-11-01 (`docs/decisions/ADR-0002_LAUNCHER_SCOPE_AND_ADDRESS_PRIVACY.md`):
both told each player the other's address. `launcher/punch.py` is gone, the server answers `punch` with a refusal, and
every match uses the relay.
