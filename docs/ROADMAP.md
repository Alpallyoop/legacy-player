# Legacy Player Roadmap

## Where things stand (November 2026, v0.7.51; changes since 0.7.47 are in [CHANGELOG.md](../CHANGELOG.md))

Two tracks share this repository:

- **The launcher (shipping).** A Windows desktop app, released through `.github/workflows/release.yml` with an installer
  (`install.ps1`, `lp.cmd`), SHA-256 sums and a build attestation (`docs/RELEASE.md`). Its scope was approved on
  2026-11-01 (`docs/decisions/ADR-0002_LAUNCHER_SCOPE_AND_ADDRESS_PRIVACY.md`, `docs/canonical/`).
- **The research track (the phases below).** Dolphin memory authority, state, events, replay and lockstep sync for
  Mario Party 4. Its status is in `docs/WBS.md` and `docs/REQUIREMENTS_TRACEABILITY.md`; the next step there is still
  the live MEM1 validation run (WBS 6).

Built in the launcher:

- Library: folder scan of 18 consoles (NES to PS3) plus Steam and Epic PC games, covers, collections, favorites,
  hidden games, filters, tags, release years and series, game cards with optional Wikipedia/Wikidata details, and a
  full-computer scan that finds game folders.
- Emulators: finding, installing and updating them from official releases after a yes, play options (screen, full
  screen, resolution and the rest), an in-game overlay, Dolphin pad profiles and game folders written for you.
- Controllers for up to four players, save folders, backups and restores, storage by console, and a doctor that
  checks what is missing.
- Online play: a lobby and relay server on the player's own PC, reached by friends through a meeting point with an
  `LP3-` server code that holds no address of that PC; rooms with invite codes, approval, a waiting line and open
  rooms; every match relayed and encrypted (RetroArch over TCP, Dolphin NetPlay as UDP inside the tunnel). No player
  sees another's address; direct links, hole punching, router opening and Tailscale were removed on 2026-11-01.
- Friends: friend codes, presence, room invites, end-to-end encrypted messages and group chats, blocking, reports and
  moderation. Since 0.7.47 they go through the host's game server with no setup, with background check-ins and tray
  notifications. A stand-alone friends service stays available for rented servers; running one on a player's own
  PC was removed (its link showed the address).
- TV mode: a full-screen, controller-first home with an intro (a start-page choice; Legacy Player opens on Home). Since 0.7.47 it has controller
  sheets for getting emulators, friends and messages, joining a friend's server and the room lobby, and Console mode
  is merged into it.
- Permissions (since 0.7.47): an enforced, versioned consent record checked in Python before every outbound or
  system-changing action, a Permissions page with undo and history, opt-in problem reports, and a first-run welcome.
- Legacy Player World themes with holiday towns, all files kept in one data folder, self-update that installs and
  restarts, a tray icon, and an uninstaller that removes only what the app created.

Not proven yet (`docs/audits/AUDIT_2026-11-01.md`, `docs/canonical/CURRENT_STATE.md`): a meeting point running for
released builds (`PUBLIC_SERVER_CODE`), real two-network play (game and friends), and the Windows pieces on real
hardware.
The audit's TV dialog double press, consent enforcement, friends reachability and controller-only TV tasks were
addressed in 0.7.47.

Done on 2026-11-01: the host address is private (`LP3-` codes through a meeting point, relay-only matches) and the
launcher's scope and canonical files are decided. Next, in order: (1) run a meeting point on a rented server and set
`PUBLIC_SERVER_CODE` in `launcher/version.py` (`docs/HOSTING_PUBLIC_SERVER.md`); (2) prove real two-network play using
`docs/MULTIPLAYER_TEST_PLAN.md`, Dolphin through the relay included; (3) walk `docs/WINDOWS_CHECKLIST.md` on real
hardware; (4) update Constellation's registry entry for `legacy-player` to the approved ownership; (5) code-sign the
exe. The phases below are the original research plan.

## Phase 0 — Repo and spec lock

Goals:

- establish public repo structure
- publish README
- publish Venture Lab pitch
- publish architecture
- publish runtime spec
- publish game pack spec
- publish legal position

Outcome:

Project is publicly understandable and properly framed.

---

## Phase 1 — Core prototype

Goals:

- establish basic runtime structure
- define first adapter interface
- define first game pack interface
- select first supported title
- select first session model

Recommended first target:

- Dolphin
- Mario Party

Outcome:

Foundation exists for first proof of online session orchestration.

---

## Phase 2 — First playable proof

Goals:

- adapter can identify target game
- session can be created and joined
- compatibility checks can run
- synchronization barrier logic exists
- replay metadata capture begins

Outcome:

First controlled multiplayer proof.

---

## Phase 3 — Runtime-assisted support

Goals:

- add scene transition coordination
- add menu synchronization barriers
- add critical state mismatch detection
- add desync diagnostics

Outcome:

System becomes robust enough to support runtime-assisted multiplayer.

---

## Phase 4 — Replay and diagnostics

Goals:

- deterministic replay package shape
- state hash checkpoints
- replay inspection tools
- stronger failure analysis surfaces

Outcome:

Legacy Player becomes useful not only for play, but also for debugging, events, and preservation.

---

## Phase 5 — Game class expansion

Goals:

- add second party-game title
- abstract shared class logic
- begin sports-game strategy exploration

Outcome:

Framework proves it can grow through reusable patterns.

---

## Phase 6 — Platform expansion

Goals:

- evaluate mGBA adapter path
- evaluate RetroArch adapter path
- formalize adapter compatibility matrix

Outcome:

Project expands from one-platform proof toward broader infrastructure.

---

## Long-term direction

Legacy Player may ultimately become:

- a retro multiplayer infrastructure platform
- a replay archive platform
- a preservation-adjacent multiplayer history tool
- a multiplayer research foundation for CDE
