# Requirements Traceability Matrix

**Baseline:** 2026-08-20

**Scope:** the LP-FR and LP-NFR rows cover the **research track** in `docs/PROJECT_SPEC.md` (baseline 2026-08-20). The
LP-LR rows at the end (added 2026-10-12) cover the shipping **launcher track**, built under Proposal 0002, which is not
yet approved.

This matrix links the working specification to current implementation evidence. `Present` means code or an artifact exists; it does not mean the requirement is complete.

| Requirement | Current implementation/evidence | Status | Primary gap or next proof |
|---|---|---|---|
| LP-FR-001 process identity | `dolphin_attach/attach.py` | PARTIAL | Executable/version authority and stronger identity |
| LP-FR-002 emulator version | Process metadata in fingerprint output | TODO | Version extraction and compatibility rule |
| LP-FR-003 version-bound game identity | `identity.json`, window-title fingerprint | PARTIAL | Revision/media hash, adapter/pack versions |
| LP-FR-004 fail unsupported profiles | `compatibility.py` | PARTIAL | Replace caller-supplied/title-only authority |
| LP-FR-005 verify adapter/pack at session gate | Session stores identifiers | GAP | Existence and compatibility verification |
| LP-FR-010 enumerate RAM candidates | `ram_map.py` | PRESENT | Complete candidate evidence fixtures |
| LP-FR-011 behavioral validation | `ram_candidate_validator.py` and offline vectors | PARTIAL | Run live action and restart/reload experiments |
| LP-FR-012 ambiguity fails closed | Strict v1 selection policy and adversarial test | PRESENT | Confirm behavior against live mirrored candidates |
| LP-FR-013 restart repeatability | Manual history only | TODO | Repeatable two-run receipt |
| LP-FR-014 RAM-relative offsets | Game-pack candidate files | PARTIAL | Remove/segregate absolute-address assumptions |
| LP-FR-015 read-only discovery | Windows access flags | PRESENT | Controlled-write authorization remains future |
| LP-FR-016 RAM receipt | Evidence/receipt producer plus recomputing verifier | PARTIAL | Preserve live receipts and add cross-run resolver receipt |
| LP-FR-020 field metadata | `STATE_FIELDS_CANDIDATES_v1.json` scaffold | PARTIAL | Type/range/lifetime/phase/evidence completeness |
| LP-FR-021 evidence promotion | Discovery notes | GAP | Enforced confidence lifecycle |
| LP-FR-022 explicit unknown | Some tools expose candidate/unknown behavior | PARTIAL | Uniform schema and tests |
| LP-FR-023 normalized-state schema | `state_model.json` phase scaffold | TODO | Full schema and transforms |
| LP-FR-024 canonical state hash | Checkpoint strings accepted by server | GAP | Define/recompute canonical state bytes |
| LP-FR-025 first board-state set | Candidate/discovery artifacts | TODO | Ground five priority fields |
| LP-FR-030 state-derived events | ADR-0001 | TODO | Implement after grounded state |
| LP-FR-031 confidence/evidence | Prototype classifier artifacts | PARTIAL | Formal event rule schema |
| LP-FR-032 unknown events | Handoff invariant | TODO | Runtime behavior and negative tests |
| LP-FR-033 deterministic event IDs/order | Replay event sequence | PARTIAL | Stable IDs independent of wall clock |
| LP-FR-034 measured classifier errors | Prototype classifier | TODO | Labeled held-out corpus |
| LP-FR-040 replay contents | `ReplayRecorder` | PARTIAL | Initial state, identity, inputs, canonical checkpoints |
| LP-FR-041 transactional replay | Atomic replace in `ReplayStore` | GAP | Limit/storage failure transactionality and durability verification |
| LP-FR-042 package digest | Replay schema string | GAP | Content digest and canonical bytes |
| LP-FR-043 independent verifier | Tests read saved JSON | GAP | Independent package/checkpoint verifier |
| LP-FR-044 safe finalization failure | `LobbyService.complete_session` | GAP | Prevent irreversible half-finalization |
| LP-FR-050 explicit authority | Participant credentials and slot map | PARTIAL | Full authority contract and reconnect identity |
| LP-FR-051 bounded ordered inputs | Lockstep coordinator | PRESENT | Broader adversarial/stale checkpoint policy |
| LP-FR-052 semantic sync boundaries | Candidate JSON and docs | TODO | Empirical boundary proof |
| LP-FR-053 divergence evidence | `DesyncTracker`, replay event | PARTIAL | Bind to recomputed canonical state |
| LP-FR-054 verified recovery | Documentation only | TODO | Choose only after determinism evidence |
| LP-FR-055 two-instance determinism | Conformance engine only | TODO | Real Dolphin long-run proof |
| LP-FR-060 versioned manifests | Several v1 JSON artifacts | PARTIAL | Formal schemas and compatibility matrix |
| LP-FR-061 complete game pack | Mario Party 4 scaffolding | TODO | Fields, phases, events, revisions, evidence |
| LP-FR-062 immutable proof references | Local capture conventions | GAP | Digest-addressed corpus references |
| LP-FR-063 pack verifier | JSON parse validation | GAP | Semantic and integrity verifier |
| LP-NFR-001 deterministic data | Sorted JSON in selected paths | PARTIAL | System-wide canonicalization contract |
| LP-NFR-002 evidence | Discovery artifacts and tests | PARTIAL | Receipt schemas and independent verification |
| LP-NFR-003 path safety | Replay path checks | GAP | Dolphin restore trusts manifest target |
| LP-NFR-004 fail closed | Several bounded validators | PARTIAL | RAM/session/live-gate gaps |
| LP-NFR-005 bounded resources | Server limits | PARTIAL | Transactional behavior when limits hit |
| LP-NFR-006 portable knowledge | RAM-relative intent | PARTIAL | Audit all persisted outputs |
| LP-NFR-007 standalone | No mandatory upstream | PRESENT | Preserve during classification |
| LP-NFR-008 clean reproducibility | `release_check.py`, workflow | PARTIAL | Commit complete tree and validate live evidence separately |
| LP-NFR-009 secrets | Credential tests | PARTIAL | Retention on replay-finalization failure |
| LP-NFR-010 claim discipline | Verification matrix and handoff | PARTIAL | Consolidate status language across older docs |

## Launcher track (LP-LR)

Added 2026-10-12 for the launcher that ships today (v0.7.46). The requirements describe what the owner asked for and
what Proposal 0002 proposes; they are not approved canonical requirements. Status words as above, plus `GREEN` for
"covered by automated tests in this sandbox". Nothing here is verified on real Windows hardware unless it says so.
Work packages are L1–L10 in `docs/WBS.md`; open findings are in `docs/audits/AUDIT_2026-10-12.md`.

| Requirement | Current implementation/evidence | Status | Primary gap or next proof |
|---|---|---|---|
| LP-LR-001 read-only library scan of the player's own folders | `launcher/scanner.py`; `tests/test_launcher.py` (files never opened, copied or changed) | GREEN | — |
| LP-LR-002 recognise each console and PC games | `launcher/consoles.py` (18 consoles plus PC), `launcher/pcgames.py`; `tests/test_pc_games.py`, `tests/test_pc_detection.py` | GREEN | Real Steam/Epic installs on Windows |
| LP-LR-003 library tools (favorites, hidden, filters, tags, covers, game details on request) | `launcher/catalog.py`, `launcher/covers.py`, `launcher/gameinfo.py`; `tests/test_library_filters.py`, `tests/test_covers_and_dats.py`, `tests/test_gameinfo.py` | GREEN | — |
| LP-LR-010 find and launch emulators without a shell | `launcher/emulators.py`, `launcher/procs.py`; `tests/test_launcher.py`, `tests/test_procs.py` | PARTIAL | Default command lines unverified for most emulators on Windows |
| LP-LR-011 install emulators only from official releases, after a yes | `launcher/engines.py`, `launcher/installer.py`, `launcher/setup.py`; `tests/test_engines.py`, `tests/test_setup.py`, `tests/test_engine_assets.py` | GREEN | First real download happens on the player's machine |
| LP-LR-012 display choices and in-game overlay | `launcher/winplace.py`, `launcher/overlay.py`; `tests/test_display_choice.py`, `tests/test_winplace.py`, `tests/test_overlay.py` | PARTIAL | Window placement is Windows-only; unverified on hardware here |
| LP-LR-020 controller mapping per console, up to four players | `launcher/controllers.py` (17 layouts), `launcher/pads.py`; `tests/test_pads_and_saves.py` | PARTIAL | RetroArch bindings from real Windows pads not verified |
| LP-LR-030 save folders, backups and restores that back up first | `launcher/saves.py`, `launcher/savefolders.py`; `tests/test_pads_and_saves.py` | GREEN | Non-RetroArch emulators keep their own folders |
| LP-LR-040 self-hosted lobby with rooms, invite codes, approval, waiting line | `server/lobby/`, `server/api/json_server.py`; `tests/test_lobby_service.py`, `tests/test_community_lobby.py`, `tests/test_waitlist.py`, `tests/test_json_server.py` | GREEN | — |
| LP-LR-041 encrypted match traffic, relayed by default | `server/relay/`, `launcher/punch.py`; `tests/test_relay.py`, `tests/test_tunnel.py`, `tests/test_punch.py`, `tests/test_retroarch_netplay.py` | PARTIAL | Real two-network play (`docs/MULTIPLAYER_TEST_PLAN.md`) |
| LP-LR-042 one server code is all a host shares; host address kept private | `launcher/servercode.py`, `launcher/portmap.py`, `launcher/reach.py`; `tests/test_together.py`, `tests/test_address_privacy.py`, `tests/test_fallback.py` | GAP | The code decodes to the host's IP; invites store it in plain text (audit 3.5) |
| LP-LR-050 friends: codes, requests, presence, invites | `server/social/`, `launcher/friends.py`; `tests/test_friends.py`, `tests/test_friends_host.py` | PARTIAL | No reachable default service across networks (audit 1.1); presence needs the window open (audit 1.2) |
| LP-LR-051 end-to-end encrypted messages and group chats | `server/social/e2e.py`, `server/social/purecrypto.py`; `tests/test_friends_crypto.py`, `tests/test_friends_e2e.py` | GREEN | Two app instances against a live service are not driven by a UI test (audit 1.5) |
| LP-LR-052 moderation behind password and authenticator codes | `server/social/admin_auth.py`, `server/social/textfilter.py`; `tests/test_friends_admin.py`, `tests/test_moderation.py` | GREEN | — |
| LP-LR-060 TV mode fully usable from a controller | `launcher/ui/index.html` (TV mode); `tests/test_tv_mode.py` | PARTIAL | Dialog double press; desktop hand-offs; no server-code entry (audit section 2) |
| LP-LR-070 player consent for every network contact, download, system change and data share | `launcher/privacy.py`, `PRIVACY.md`; `tests/test_privacy.py`, `tests/test_engines.py` (downloads refused when off) | GAP | Record not enforced in Python; actions without an item; some on by default (audit section 3) |
| LP-LR-071 opt-in, scrubbed problem reports | `launcher/reports.py`, `server/report_receiver.py`; `tests/test_reports.py` | GREEN | — |
| LP-LR-080 self-update that checks the download and restarts | `launcher/selfupdate.py`, `launcher/updateall.py`; `tests/test_selfupdate.py`, `tests/test_update_all.py` | PARTIAL | Replacing the running app on Windows not verified here |
| LP-LR-081 uninstall removes only what the app created | `launcher/selfuninstall.py`; `tests/test_uninstall_created.py` | GREEN | — |
| LP-LR-090 release only from tested commits, with hashes and attestation | `.github/workflows/release.yml`, `tools/release_check.py`, `tools/package_release.ps1`, `install.ps1`; `tests/test_release_files.py` | PARTIAL | No code-signing certificate yet |
| LP-LR-091 local web UI accepts only its own page | `launcher/web.py`; `tests/test_launcher.py`, `tests/test_hardening.py`, `tests/test_web_lifecycle.py` | GREEN | — |
| LP-LR-092 every file in one data folder | `launcher/datadir.py`; `tests/test_datadir.py` | GREEN | — |
