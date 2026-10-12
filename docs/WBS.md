# Legacy Player Work Breakdown Structure

**Baseline date:** 2026-08-20  
**Planning horizon:** Tier-0 through platform-generality proof  
**Status vocabulary:** `GREEN`, `PARTIAL`, `NEXT`, `TODO`, `BLOCKED`, `HISTORICAL`

**Scope:** WBS 0–25 cover the **research track** (Dolphin memory authority, state, events, replay and lockstep sync for
Mario Party 4), as baselined on 2026-08-20. The shipping **launcher track** (Proposal 0002, not yet approved) has its own
work packages, L1–L10, at the end of this file (added 2026-10-12).

Status means evidence available in the current working tree, not product completion. A work package is complete only when its exit evidence satisfies `docs/DEFINITION_OF_DONE.md`.

## Delivery sequence

```text
governance
  -> RAM authority
  -> field grounding
  -> normalized state
  -> semantic events
  -> verified replay
  -> local synchronization
  -> network synchronization/recovery
  -> game-pack freeze
  -> second-game and second-emulator proofs
```

## Work-package summary

| WBS | Work package | Current status | Depends on | Exit evidence |
|---|---|---|---|---|
| 0 | Governance and contracts | PARTIAL | — | Approved identity, version policies, schemas, release policy |
| 1 | Emulator process adapter | PARTIAL | 0 | Adapter contract tests and verified process/version receipt |
| 2 | Game identification | PARTIAL | 1 | Version/media-bound game identity receipt |
| 3 | Raw RAM mapping | GREEN prototype | 1 | Complete candidate enumeration vectors |
| 4 | Raw memory observation | PARTIAL | 3 | Deterministic read/snapshot benchmarks and failure tests |
| 5 | Mutation discovery | PARTIAL | 4 | Revalidated labeled mutation corpus |
| 6 | Behavioral MEM1 validation | PARTIAL/NEXT LIVE | 2–5 | Repeatable unambiguous RAM-resolution receipt |
| 7 | Mario Party 4 discovery corpus | PARTIAL | 6 | Versioned positive and negative action corpus |
| 8 | State-field discovery | TODO | 6–7 | Grounded field registry |
| 9 | Discovery signature engine | HISTORICAL/partial | 5–8 | Discovery-only classifier metrics |
| 10 | Phase engine | TODO | 8 | Verified phase registry and transition receipts |
| 11 | Normalized game state | TODO | 8–10 | Schema, canonical bytes, state hash, diff vectors |
| 12 | Semantic event engine | TODO | 10–11 | Labeled event corpus and measured error rates |
| 13 | Replay and markers | PARTIAL | 11–12 | Verified replay package and independent receipt |
| 14 | Determinism experiments | TODO | 6, 11, 13 | Repeated two-run and two-instance evidence |
| 15 | Multiplayer synchronization | PARTIAL prototype | 11, 14 | Boundary sync and divergence evidence |
| 16 | Recovery/resynchronization | TODO | 13–15 | Proven recovery and failure receipts |
| 17 | Game-pack format | PARTIAL scaffold | 0, 8–13 | Schema-valid verified pack |
| 18 | Second-game proof | TODO | 17 | Second title without core title-specific changes |
| 19 | Second-emulator proof | TODO | 1, 17–18 | Second adapter conformance evidence |
| 20 | Runtime APIs | PARTIAL prototype | 11–17 | Versioned API contracts and negative tests |
| 21 | Operator experience | TODO | 6, 11, 13 | Guided local workflow without shell expertise |
| 22 | Packaging and release | TODO | 0, 17, 20–21 | Clean-install, signed-package, rollback evidence |
| 23 | Security and safety | PARTIAL | all | Closed high risks and verified threat controls |
| 24 | Test infrastructure | PARTIAL | all | Offline fixtures, adversarial suites, clean CI |
| 25 | Mario Party 4 vertical completion | TODO | 6–17, 20, 23–24 | Frozen v1 game pack and Tier-0 receipt |

## WBS 0 — Governance and contracts

- 0.1 Approve service classification and ownership boundaries.
- 0.2 Define repository structure and dependency rules.
- 0.3 Define semantic versioning for runtime, adapters, schemas, and game packs.
- 0.4 Define canonical serialization and hash policy.
- 0.5 Define evidence, receipt, retention, and redaction policy.
- 0.6 Freeze adapter and game-pack compatibility rules.
- 0.7 Define release channels, claim levels, and rollback policy.
- 0.8 Establish requirements traceability and risk ownership.

Exit: Proposal 0001 is approved; registry and canonical integration files are updated together; tests and receipt exist.

## WBS 1–5 — Observation substrate

### 1. Emulator process adapter

- Process discovery, ambiguity handling, read permissions, metadata, version fingerprint, safe detach, adapter conformance.
- Current evidence: Dolphin process discovery and read-only memory access exist.
- Gap: process name and window title are not sufficient identity authority.

### 2. Game identification

- Running-title detection, region, revision, media/executable fingerprint, pack compatibility gate.
- Current evidence: `GMPE01`/USA title parsing prototype.
- Gap: revision/media identity and independent verification.

### 3. Raw RAM mapping

- Enumerate readable regions; classify mapped/private regions; exact-size and zero-content screening; retain all plausible candidates.
- Current evidence: exact 32 MiB candidates can be rediscovered.
- Constraint: static candidate ranking is not authoritative.

### 4. Raw memory observation

- Arbitrary reads, page reads, sparse deterministic windows, full-MEM1 scanning, timed capture, performance and read-error behavior.
- Exit: deterministic fixtures cover complete, partial, unreadable, changed, and unchanged reads.

### 5. Mutation discovery

- Baseline/post capture, repeated snapshots, page hashing, byte-offset extraction, temporal profiles, labeled action experiments.
- Existing v1 hot-page and action-pattern artifacts remain historical evidence until remapped to validated MEM1.

## WBS 6 — Behavioral MEM1 validation

This is the immediate critical work package.

The offline evaluator, evidence/receipt format, strict ambiguity policy, separate
verifier, and adversarial tests are implemented. A live action run and restart/reload
repeatability proof remain outstanding.

- 6.1 Enumerate every exact mapped 32 MiB candidate.
- 6.2 Capture identical deterministic sample positions from each candidate.
- 6.3 Record baseline samples and hashes.
- 6.4 Execute a documented known-action experiment.
- 6.5 Capture multiple post-action samples.
- 6.6 Calculate mutation, content, sentinel, and fingerprint signals independently.
- 6.7 Rank candidates with an explainable confidence model.
- 6.8 Fail if no candidate or more than one candidate satisfies authority criteria.
- 6.9 Repeat after game reload.
- 6.10 Repeat after Dolphin restart, allowing the absolute base to change.
- 6.11 Emit and independently verify a RAM-resolution receipt.
- 6.12 Add offline regression vectors and a self-test.

Exit tokens:

- `DOLPHIN_RAM_CANDIDATE_VALIDATED`
- `DOLPHIN_RAM_RESOLVER_REPEATABLE`
- `LEGACY_PLAYER_DOLPHIN_MEM1_AUTHORITY_GREEN`

## WBS 7–12 — State understanding

### 7. Discovery corpus

Capture positive, repeated-positive, negative, and confounding cases for menu actions, board load, dice, movement, landing, economy changes, items, stars, Boo, board events, minigames, turns, and game completion.

### 8. State-field discovery

For each field:

1. Find candidate RAM-relative offsets.
2. Demonstrate a positive change.
3. Repeat independently.
4. Run negative and confounding controls.
5. Determine datatype, width, endianness, range, lifetime, and phase.
6. Bind to game/revision/adapter/pack versions.
7. Promote through the evidence confidence states.

Priority fields: P1 coins, P1 stars, P1 board position, current player, turn number; then all players, dice, movement, items, star location, event state, phase, and minigame ID.

### 9. Discovery signature engine

Retain page clusters, byte-count buckets, and offset patterns as field-discovery aids. Add collision analysis, action-specific subtraction, negative scoring, confidence, and explicit unknown classification. Do not expose these patterns as the final semantic API.

### 10. Phase engine

Define versioned phases, permitted transitions, phase confidence, field validity by phase, illegal-transition handling, and transition receipts.

### 11. Normalized state

Create schema, raw-to-normalized transforms, confidence metadata, snapshot, canonical serialization, SHA-256 state hash, diff, and core state API.

### 12. Semantic events

Derive candidate and semantic events from normalized deltas plus phase context. Specify deterministic IDs, ordering, payloads, confidence, journal behavior, and measured false-positive/false-negative rates.

Exit tokens:

- `LEGACY_PLAYER_MP4_COINS_FIELD_GREEN`
- `LEGACY_PLAYER_MP4_BOARD_STATE_GREEN`
- `LEGACY_PLAYER_MP4_EVENT_ENGINE_GREEN`

## WBS 13–17 — Replay, determinism, and game packs

### 13. Replay

- Versioned marker schema, initial-state binding, input/event binding, checkpoint hashes, transcript, atomic store, independent verifier, corruption/replay/stale tests.

### 14. Determinism experiments

- Identical save-state and input trials; RNG, timer, frame, emulator-version, and nondeterminism classification; validated deterministic boundaries.

### 15. Multiplayer synchronization

- Authoritative state, peer identities, input ownership, validated boundaries, digests, divergence handling, host migration, reconnect, spectators, latency, and WAN experiments.

### 16. Recovery/resynchronization

- Verified checkpoints, save-state feasibility, controlled correction investigation, replay from checkpoint, deterministic recovery, and explicit failure receipts.

### 17. Game-pack format

- Manifest, immutable identity, supported revisions, adapter constraints, fields, phases, events, markers, boundaries, evidence references, schemas, verifier, self-tests, and freeze receipt.

Exit tokens:

- `LEGACY_PLAYER_MP4_REPLAY_GREEN`
- `LEGACY_PLAYER_MP4_LOCAL_SYNC_GREEN`
- `LEGACY_PLAYER_MP4_NETWORK_SYNC_GREEN`
- `LEGACY_PLAYER_MP4_GAME_PACK_V1_GREEN`

## WBS 18–24 — Generalization and productization

- **18 Second game:** Prove adapter reuse and game-pack isolation.
- **19 Second emulator:** Prove the adapter contract without core redesign.
- **20 APIs:** Version session, state, event, replay, sync, diagnostics, adapter, and pack APIs.
- **21 UX:** Emulator detection, support status, state inspector, diagnostics, lobby, replay browser, and discovery mode.
- **22 Packaging:** Dependency isolation, Windows distribution, adapter/pack distribution, update and rollback, signed releases.
- **23 Security:** Process access, read-only default, write authorization, authentication, replay/pack integrity, malicious-pack containment, audit trails.
- **24 Tests:** Unit, parser, memory fixtures, offline mutation/classifier vectors, replay vectors, adapter/pack contracts, adversarial tests, regression and clean CI.

## WBS 25 — Mario Party 4 vertical completion

Integrate the MEM1 resolver, field/phase/event registries, normalized state, replay, sync boundaries, digests, local/LAN/WAN experiments, recovery, compatibility matrix, proof corpus, and pack freeze.

## Immediate executable backlog

| Order | Deliverable | Dependency | Evidence required |
|---:|---|---|---|
| 1 | `ram_candidate_validator.py` design and implementation | WBS 3–5 | Unit tests and candidate receipt fixture |
| 2 | Live authoritative-MEM1 experiment | 1 | Signed/digested raw receipt plus operator notes |
| 3 | Restart/reload persistence experiment | 2 | Two independent matching resolver receipts |
| 4 | Re-run controlled page sweeps | 3 | Version-bound capture set |
| 5 | Produce `HOT_RAM_WINDOWS_v2.json` | 4 | Schema validation and provenance references |
| 6 | Implement iterative value narrowing | 3–5 | Offline fixtures and negative tests |
| 7 | Ground P1 coins | 6 | Positive, repeated, negative, restart proofs |
| 8 | Ground P1 stars | 6 | Same evidence standard |
| 9 | Ground P1 board position | 6 | Same evidence standard |
| 10 | Ground current player and turn | 6 | Same evidence standard |
| 11 | Implement normalized state watcher | 7–10 | Deterministic snapshot/diff vectors |
| 12 | Derive first semantic events | 11 | Labeled corpus and measured errors |

## Launcher track (L1–L10)

Added 2026-10-12. These packages describe the launcher that ships today (v0.7.46). It is built under Proposal 0002,
which is still "Proposed (not approved)"; see `docs/proposals/2026-10-12-launcher-approval-and-canonical-docs.md`. The
same status words are used. `GREEN` here means automated tests cover it in this sandbox; nothing in this track has an
independent receipt, and the Windows-only pieces are not verified on real hardware (`docs/WINDOWS_CHECKLIST.md`).
Open findings come from `docs/audits/AUDIT_2026-10-12.md`.

| WBS | Work package | Status | Code | Test evidence | Open gap |
|---|---|---|---|---|---|
| L1 | Library | GREEN | `launcher/scanner.py`, `launcher/catalog.py`, `launcher/covers.py`, `launcher/datfiles.py`, `launcher/gamefinder.py`, `launcher/pcscan.py`, `launcher/pcgames.py`, `launcher/gamecard.py`, `launcher/gameinfo.py` | `tests/test_launcher.py`, `tests/test_library_filters.py`, `tests/test_gamefinder.py`, `tests/test_covers_and_dats.py`, `tests/test_pc_games.py`, `tests/test_pc_detection.py`, `tests/test_pc_manage.py`, `tests/test_gamecard.py`, `tests/test_gameinfo.py` | Real Steam/Epic installs on Windows |
| L2 | Emulators: find, install, launch, display | PARTIAL | `launcher/emulators.py`, `launcher/engines.py`, `launcher/installer.py`, `launcher/setup.py`, `launcher/winplace.py`, `launcher/overlay.py`, `launcher/overlay_window.py`, `launcher/dolphinpads.py`, `launcher/dolphinpaths.py` | `tests/test_engines.py`, `tests/test_engine_assets.py`, `tests/test_setup.py`, `tests/test_display_choice.py`, `tests/test_winplace.py`, `tests/test_overlay.py`, `tests/test_overlay_window.py`, `tests/test_dolphin_pads.py`, `tests/test_dolphin_paths.py` | Command lines and window placement unverified on real Windows for most emulators |
| L3 | Controllers | PARTIAL | `launcher/controllers.py`, `launcher/pads.py`, `launcher/keyboard.py` | `tests/test_pads_and_saves.py` | RetroArch bindings from Windows controller input not verified on real hardware |
| L4 | Saves and storage | GREEN | `launcher/saves.py`, `launcher/savefolders.py` | `tests/test_pads_and_saves.py`, `tests/test_general_fixes.py` (storage wording) | Emulators other than RetroArch keep their own save folders |
| L5 | Rooms, relay and server codes | PARTIAL | `server/lobby/`, `server/relay/`, `server/api/json_server.py`, `server/cli.py`, `launcher/servercode.py`, `launcher/punch.py`, `launcher/portmap.py`, `launcher/reach.py`, `launcher/lobby_client.py` | `tests/test_lobby_service.py`, `tests/test_community_lobby.py`, `tests/test_waitlist.py`, `tests/test_relay.py`, `tests/test_json_server.py`, `tests/test_server_tls_and_control.py`, `tests/test_tunnel.py`, `tests/test_punch.py`, `tests/test_portmap.py`, `tests/test_fallback.py`, `tests/test_together.py`, `tests/test_address_privacy.py`, `tests/test_retroarch_netplay.py` | Real two-network play unproven; a server code decodes to the host's address (audit 3.5) |
| L6 | Friends and messages | PARTIAL | `server/social/` (service, `e2e.py`, `purecrypto.py`, `admin_auth.py`), `launcher/friends.py`, `launcher/socialhost.py` | `tests/test_friends.py`, `tests/test_friends_crypto.py`, `tests/test_friends_e2e.py`, `tests/test_friends_admin.py`, `tests/test_friends_host.py`, `tests/test_moderation.py` | No reachable default service, so friends on different networks usually cannot connect (audit 1.1); presence needs the window open |
| L7 | TV mode | PARTIAL | `launcher/ui/index.html` (TV mode section) | `tests/test_tv_mode.py` | Dialog double press; many tasks hand off to desktop pages a controller cannot use (audit section 2) |
| L8 | Consent and privacy | PARTIAL | `launcher/privacy.py`, `launcher/catalog.py` (settings), `launcher/reports.py`, `PRIVACY.md` | `tests/test_privacy.py`, `tests/test_reports.py`, `tests/test_engines.py` (downloads gated) | The consent record is not enforced before acting; several actions have no item or are on by default (audit section 3) |
| L9 | Self-update and uninstall | PARTIAL | `launcher/selfupdate.py`, `launcher/updateall.py`, `launcher/selfuninstall.py` | `tests/test_selfupdate.py`, `tests/test_update_all.py`, `tests/test_uninstall_created.py` | Replacing the running app and restarting is Windows-specific and not verified on real hardware in this sandbox |
| L10 | Release pipeline and install | PARTIAL | `.github/workflows/release.yml`, `tools/package_release.ps1`, `tools/release_check.py`, `install.ps1`, `lp.ps1`, `lp.cmd`, `build_exe.bat` | `tests/test_release_files.py`, `tests/test_hardening_r5.py` | The test suite runs on `windows-latest` in the release workflow; no code-signing certificate yet (`docs/CODE_SIGNING_POLICY.md`) |

Cross-cutting: the app window and local web server (`launcher/web.py`, `launcher/tray.py`; `tests/test_web_lifecycle.py`,
`tests/test_ui_smoke.py`, `tests/test_hardening.py`), the data folder (`launcher/datadir.py`; `tests/test_datadir.py`)
and readable contrast (`tools/contrast_check.py`; `tests/test_contrast.py`, `tests/test_world.py`).
