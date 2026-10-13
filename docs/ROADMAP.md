# Legacy Player Roadmap

## Where things stand (October 2026, v0.7.46; the 0.7.47 work is in [CHANGELOG.md](../CHANGELOG.md))

Two tracks share this repository:

- **The launcher (shipping).** A Windows desktop app, released through `.github/workflows/release.yml` with an installer
  (`install.ps1`, `lp.cmd`), SHA-256 sums and a build attestation (`docs/RELEASE.md`). It is built under Proposal 0002,
  which is still not approved (`docs/proposals/2026-10-12-launcher-approval-and-canonical-docs.md`).
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
- Online play: a lobby and relay server on the player's own PC, one server code to share, rooms with invite codes,
  approval, a waiting line and open rooms; encrypted RetroArch match traffic, relayed by default, with direct
  (hole-punched) links as an opt-in; automatic router opening and a shared-server fallback.
- Friends: friend codes, presence, room invites, end-to-end encrypted messages and group chats, blocking, reports and
  moderation. Since 0.7.47 they go through the host's game server with no setup, with background check-ins and tray
  notifications; a separate service (one-click hosting of your own) stays the advanced option.
- TV mode: a full-screen, controller-first home with an intro (a start-page choice; Legacy Player opens on Home). Since 0.7.47 it has controller
  sheets for getting emulators, friends and messages, joining a friend's server and the room lobby, and Console mode
  is merged into it.
- Permissions (since 0.7.47): an enforced, versioned consent record checked in Python before every outbound or
  system-changing action, a Permissions page with undo and history, opt-in problem reports, and a first-run welcome.
- Legacy Player World themes with holiday towns, all files kept in one data folder, self-update that installs and
  restarts, a tray icon, and an uninstaller that removes only what the app created.

Not proven yet, and open items from the 12 October audit (`docs/audits/AUDIT_2026-10-12.md`): real two-network play
(game and friends), the Windows pieces on real hardware, and a server code that still contains the host's address.
The audit's TV dialog double press, consent enforcement, friends reachability and controller-only TV tasks were
addressed in 0.7.47.

Next, in order: (1) keep the host address private (an opaque server code instead of an encoded address, which needs
a decision on where a rendezvous runs); (2) prove real two-network play using
`docs/MULTIPLAYER_TEST_PLAN.md`; (3) walk `docs/WINDOWS_CHECKLIST.md` on real hardware; (4) a decision on Proposal 0002
and the missing canonical files; (5) code-sign the exe. The phases below are the original research plan.

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
