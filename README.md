# Legacy Player

A self-hosted, console-like launcher for legacy games. It finds your games, starts them in the right emulator, maps your
controllers, backs up your saves, and lets friends play together online with one server code and room invite codes.

Legacy Player does not include any game content, BIOS files or emulators. You use your own legally obtained games; the app
can download emulators from their official release pages when you ask it to.

It is local-first: everything runs on your own Windows computer. The multiplayer server runs on one player's PC (no
rented server), friends and messages go through that same server, and nothing goes online or changes your computer
until you allow it (each permission is explained when it is first needed, and listed on the Permissions page).

**Read more:** [User guide](docs/USER_GUIDE.md) · [Changelog](CHANGELOG.md) · [Privacy](PRIVACY.md) ·
[Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) · [Running from source](docs/RUNNING_LOCALLY.md) ·
[All documentation](docs/PROJECT_DOCUMENTATION_INDEX.md)

## Quick start

1. **Install** with one line in PowerShell (details and other ways [below](#install-windows)):
   `irm https://raw.githubusercontent.com/Alpallyoop/legacy-player/main/install.ps1 | iex`
2. **First run.** The doctor asks your name, where your games are, scans for emulators you already have, and lists the
   permissions with nothing ticked. Get missing emulators under Configure > Engines, or the Get emulators tile in
   TV mode.
3. **Join a friend.** Ask the host for their server code (`LP-...`). Servers > "Joining a friend? Paste their server
   code" > Connect (in TV mode: Online > Join a friend's server). Then join their room with its invite code.
4. **Host.** Servers > tick "Let friends connect" > Start, allow the router and firewall permissions, then Show server
   code > Copy and send it to your friends privately. Host a room from a game's Online button. A server code contains
   your server's address, so give it only to people you trust.
5. **Friends.** Friends > Get my friend code. Your friends list lives on the server you are connected to, so it works
   wherever the game does.

The [user guide](docs/USER_GUIDE.md) explains each step, the TV-mode controller buttons and what to do when friends
can't connect.

## Install (Windows)

PowerShell, no administrator needed. Either one line:

```powershell
irm https://raw.githubusercontent.com/Alpallyoop/legacy-player/main/install.ps1 | iex
```

From **Command Prompt (cmd)**, **Windows Terminal**, **Git Bash** or **WSL** (anything that can run `powershell.exe`), the same install in one line:

```
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/Alpallyoop/legacy-player/main/install.ps1 | iex"
```

(In Git Bash or WSL write `powershell.exe` instead of `powershell`.) Legacy Player is a Windows app, so there is no macOS or Linux install.

or, through git, with the small `lp` command that comes with the repository:

```powershell
git clone https://github.com/Alpallyoop/legacy-player
cd legacy-player
.\lp.cmd install        # newest release; or  .\lp.cmd install v0.7.49  for one exact version
.\lp.cmd run            # later:  .\lp.cmd update | version | path | uninstall | help
```

In PowerShell type `.\lp.cmd`: a plain `.\lp` runs `lp.ps1`, which Windows' default execution policy (Restricted) refuses
to run. `lp.cmd` starts it with `-ExecutionPolicy Bypass` for you. In Command Prompt plain `lp install` works. Without
`lp.cmd`: `powershell -ExecutionPolicy Bypass -File .\lp.ps1 install`.

Both download the release from [Releases](https://github.com/Alpallyoop/legacy-player/releases), check its SHA-256, install to
`%LOCALAPPDATA%\Programs\LegacyPlayer`, add a Start menu shortcut and open the app. Or download the files yourself: each
release has `LegacyPlayer-<version>-win64.zip` (the app folder: `LegacyPlayer.exe`, its `_internal` folder and a read-me)
with a `.sha256` and a combined `SHA256SUMS.txt`; unzip it anywhere you like and keep the files together.

**Where your files go.** Legacy Player keeps everything it saves (settings, the emulators it downloads, saves, covers,
temporary files and logs) in one folder: `LegacyPlayerData` inside the Legacy Player folder (`data` in a git checkout run
with `lp source`). Nothing goes to your user folders. To use another folder, press Change under Settings > Where Legacy
Player keeps its files (it copies, checks, then removes the old folder), or start it with `--data-dir "D:\Some Folder"`.
The logs can go to a folder of their own the same way. Version 0.7.44 and older used `%USERPROFILE%\.legacy-player`; the
app offers once to move those files into its own folder. Releases are signed only once a code-signing certificate has been added (see
`docs/RELEASE.md`); until then Windows SmartScreen says "unknown publisher": More info, then Run anyway. Every release lists its
SHA-256 hashes and carries a GitHub build attestation. See `docs/RELEASE.md`.

## What it does

- **Library:** scans your folders, recognises 18 consoles (NES to PS3) plus your Steam and Epic PC games, covers,
  collections, favorites, hidden games, filters, tags, release years and series, per-game settings. Each game shows how
  many people can play it and whether it is single-player, co-op or versus.
- **TV mode:** a full-screen home made for the couch, driven with a controller (A select, B back, X options, Y search,
  LB/RB rows, RT play, Start menu) or the keyboard. Legacy Player opens on Home; you can choose TV mode as the page it
  opens to (it then starts with a short intro you can skip); F11, the Guide button or holding Back + Start opens it any time. Getting emulators, friends and messages,
  joining a friend's server and the room lobby all work there with the controller, and a page that opens in the
  normal window can be used with the controller too (B goes back to TV mode). It replaces the old Console mode.
- **Emulators:** finds or installs them (RetroArch, Dolphin, mGBA, DuckStation, PCSX2 and others), full-screen and
  controller options per emulator, Dolphin pad profiles written for you (and restorable).
- **Quick play:** hover a game's cover and it splits into Play and Online (host a room or join with a code).
- **Play options:** before a game opens (or any time from "Play with options…"): full screen or a window, which screen,
  resolution, borderless, vsync, sharp pixels and the rest, plus "Optimize for my computer". Remember it per emulator or be asked.
- **Legacy Player World themes:** eight original places (Martin's Meadow, Pixel Harbor, Ember Peaks, Frostfall, Mirage Dunes,
  Glimmerwood, Neon Arcade, Cloudtop Isles), each with its own day and night colours and an animated 8-bit scene behind
  the app. Day, Night, or Follow my clock (day from 7:00 to 19:00). Four holiday towns (Spooky Hollow, Pumpkin Town, Winter Lights, New Year) take over on their dates (you can turn that off).
- **Game cards:** each game has a card with region, revision, players, release date, makers and a description
  (looked up from Wikipedia/Wikidata only when you ask; you can write your own).
- **Friends (optional):** friend codes, who is online, room invites, and end-to-end encrypted messages and group chats
  (the server can't read them). No accounts for players. With nothing to set up, your friends list lives on the
  multiplayer server you are connected to (your own, or the friend's server you joined), over its encrypted
  connection; the host moderates it. Legacy Player checks in for you in the background and shows a tray notification
  for a new message, request or invite while the window is closed. Only friends can message you; requests need your
  code and can be switched off. Report a player or a single message, block, and a word filter you can turn on or off
  (Settings > Friends). Advanced: a separate friends service keeps one list across servers; run one with one click
  (Friends > Run a friends service on this computer) and moderate it in the app or in a web console behind a password
  and authenticator codes ([hosting](docs/HOSTING_PUBLIC_SERVER.md), [friends security](docs/FRIENDS_SECURITY.md)).
- **Updates:** Account > Update everything (or Check for updates) downloads the new Legacy Player, checks it, and
  restarts on it. A copy run from a git folder pulls and restarts instead.
- **See an issue or a problem?** on the Home page writes a categorised report (scrubbed first). It is sent only when a
  report address is set (Settings > Privacy > Send reports to). Released builds have none built in, so until one is set the
  report stays on your computer (Settings > Problem reports).
- **Games open where you want:** in front of Legacy Player, full screen or windowed, on the screen you pick (asked once per emulator,
  changeable under Display and video > Where games open).
- **In-game overlay:** press Ctrl+Shift+L, or hold Back + Start on an Xbox-style controller, for a small window over any game with
  Force quit, full screen/windowed and your room code. Both binds can be changed in Settings. Force quit also sits next to
  "game running" in the app.
- **Controllers:** pad and keyboard mapping per console, up to four players.
- **Saves:** finds each emulator's save files, one-click backups and restores.
- **Play together:** everything is on the Servers page: join a friend's server, your server and Server info (with the
  network test) side by side, and the rooms below.
  - Start the server with "Let friends connect". With your permission the app asks your router (UPnP) to open the
    port and adds the Windows Firewall rule, and puts your address in a short server code (`LP-...`). Friends paste
    the code to connect. Anyone with the code can read the address in it, so share it only with people you trust.
  - Rooms have invite codes, approval, a waiting line and open rooms. Game traffic is encrypted between players.
  - If your connection cannot be reached from outside (hotspot, provider-shared address), the app moves to a shared relay
    server when one is set (see `docs/HOSTING_PUBLIC_SERVER.md`).
- **Permissions:** everything that goes online or changes your computer is a permission of its own, off until you
  allow it, and checked before every action. A box explains each one the first time; the Permissions page (Account >
  Permissions) shows them all, lets you turn any off (undoing what it can) and keeps a dated history
  ([PRIVACY.md](PRIVACY.md)).
- **Problem reports (opt in):** off by default. If something fails, the app asks once and shows exactly what would be sent;
  names, IP addresses, codes and folder paths are removed first (`docs/proposals/2026-10-07-audit-and-fixes.md`).
- **Tools:** computer specs, network check, Dolphin memory probe (any GameCube or Wii game), storage by console, a doctor
  that checks what is missing, and an uninstaller that removes only what Legacy Player created. The doctor asks whether to keep or delete the save folders he made, and leaves you a prescription.
- Close the window with X and it stays in the tray with the server running; right-click the tray icon for server controls.

## Honest status

What is verified: the launcher, library, saves, settings, server, rooms, relay, friends and TV mode code are covered by
automated tests (more than 800) and a headless-browser click-through of every page.

The latest audit, [docs/audits/AUDIT_2026-10-12.md](docs/audits/AUDIT_2026-10-12.md), found three big gaps; the work
since then (see [CHANGELOG.md](CHANGELOG.md)) checks consent before every action, carries friends over the game server
so they work wherever the game does, and lets TV mode do its tasks with a controller. Still open: a server code still
contains the host's address, and none of this has been tried between two real networks yet. The launcher is built
under a proposal that is not approved yet
([docs/proposals/2026-10-12-launcher-approval-and-canonical-docs.md](docs/proposals/2026-10-12-launcher-approval-and-canonical-docs.md)).

What is not yet verified on real hardware: the Windows pieces (tray menu, Recycle Bin move, Dolphin pad names, firewall
rule, memory probe), opening a real router, a real shared server, and actual online play between two networks. Netplay
quality varies by console: NES, SNES, Genesis, Game Boy and GBA are the best fit; N64, PS1 and DS are experimental;
GameCube and Wii work per game and need a game pack (Mario Party 4 is the first). See `docs/NETPLAY_BY_CONSOLE.md`,
`docs/WINDOWS_CHECKLIST.md` and `docs/MULTIPLAYER_TEST_PLAN.md`.

## Run from source

Python 3.13+ (the Dolphin memory probe also needs `pip install psutil`; the packaged exe already has it). Everything
about running from source, the server and friends service on their own, where files go and building the exe is in
[docs/RUNNING_LOCALLY.md](docs/RUNNING_LOCALLY.md); how to contribute and run the tests is in
[CONTRIBUTING.md](CONTRIBUTING.md).

```powershell
python -m launcher --games "D:\Games"       # opens the app; add folders inside it too
python -m server.cli start --port 8765       # a standalone server (see docs/HOSTING_PUBLIC_SERVER.md)
python -m unittest discover -s tests         # the tests
.\build_exe.bat                              # builds dist\LegacyPlayer.exe
powershell -File tools\package_release.ps1   # builds the release zip
```

## Repository layout

```text
launcher/     the app: library, emulators, controllers, saves, settings, tray, UI (launcher/ui/index.html)
server/       lobby and room service, relay, admin CLI, problem-report receiver
adapters/     emulator adapters (Dolphin, RetroArch) and netplay launch logic
runtime/      session, sync, state, desync and replay engine
frontend/     input and controller delivery
game_packs/   per-game data (Mario Party 4 first)
tools/        memory probe, release packaging, report reader, Windows self-check, contrast check
docs/         specs, plans, decisions, audits, release and test guides
tests/        automated tests
```

## How it is designed

Legacy Player is a common multiplayer runtime plus platform adapters plus per-game packs plus self-hostable
infrastructure. It is not one plugin that magically works for every game. Support comes in tiers:

- **Tier A, native sync:** games that already work under emulator lockstep. Legacy Player adds hosting, rooms,
  compatibility checks, diagnostics.
- **Tier B, runtime assisted:** games that need menu barriers, controller remapping or state checks.
- **Tier C, full conversion:** games that need heavy orchestration to become remotely playable.

Read `docs/ARCHITECTURE.md`, `docs/RUNTIME_SPEC_v1.md` and `docs/GAME_PACK_SPEC_v1.md`; the documentation index is
`docs/PROJECT_DOCUMENTATION_INDEX.md`.

## Legal position

Legacy Player is an interoperability project. It does not distribute copyrighted game data, proprietary assets, ROMs,
ISOs or BIOS files, claim ownership of any game, or require redistribution of game binaries. Users bring their own legally
obtained games and emulator environments. See `docs/LEGAL_POSITION.md`.

## Venture Lab role

Legacy Player is a Venture Lab project with product and research value: a real multiplayer instrument for classic games,
self-hosted community infrastructure, and a multiplayer knowledge base for the Clio Development Engine (CDE).

## License, privacy and security
MIT licensed ([LICENSE](LICENSE); third-party notes in [THIRD_PARTY.md](THIRD_PARTY.md)). What the app does with
information: [PRIVACY.md](PRIVACY.md) (nothing leaves your computer unless you choose). Reporting a vulnerability:
[SECURITY.md](SECURITY.md). Code signing: [docs/CODE_SIGNING_POLICY.md](docs/CODE_SIGNING_POLICY.md).

## Contributing

Bug reports, ideas and pull requests are welcome: read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md). What changed in each release: [CHANGELOG.md](CHANGELOG.md).
