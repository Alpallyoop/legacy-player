# Legacy Player Documentation Index

**Updated:** 2026-10-12

Every document in the repository, grouped by who it is for. It also says which document governs which question, so
older planning documents are not mistaken for current proof. `tools/check_links.py` (run by
`tests/test_doc_links.py`) checks that every relative link in these documents works.

- [Players](#players)
- [Hosting](#hosting)
- [Contributors](#contributors)
- [Research track](#research-track)
- [Governance](#governance)
- [Audits](#audits)

## Players

| Document | What it answers |
|---|---|
| [README.md](../README.md) | What Legacy Player is, how to install it, quick start, what it does today. |
| [USER_GUIDE.md](USER_GUIDE.md) | Plain-language guide: first run, permissions, games, emulators, controllers, TV mode buttons, playing with a friend, friends and messages, updates, troubleshooting, reporting a problem. |
| [CHANGELOG.md](../CHANGELOG.md) | What changed in each release. |
| [PRIVACY.md](../PRIVACY.md) | What leaves your computer, when, and to whom; every permission; what a server code reveals. |
| [SECURITY.md](../SECURITY.md) | How to report a vulnerability. |
| [NETPLAY_BY_CONSOLE.md](NETPLAY_BY_CONSOLE.md) | How online play works for each console, and its limits. |
| [PRIVATE_LINK.md](PRIVATE_LINK.md) | Dolphin online play over Tailscale (encrypted, no router set-up). |
| [FRIENDS_SECURITY.md](FRIENDS_SECURITY.md) | Friends and messages: end-to-end encryption, what the server can see, reports, the moderation console. |
| [LEGAL_POSITION.md](LEGAL_POSITION.md) | Bring your own games: what the project does and does not distribute. |
| [THIRD_PARTY.md](../THIRD_PARTY.md) | Third-party notices. |

## Hosting

| Document | What it answers |
|---|---|
| [HOSTING_PUBLIC_SERVER.md](HOSTING_PUBLIC_SERVER.md) | Run a shared server, the problem-report receiver and a separate friends service. |
| [deploy/README.md](../deploy/README.md) | The ready-to-run server kit (Docker, Caddy, systemd) and the deployment checker. |
| [server/README.md](../server/README.md) | The multiplayer server: start, stop, status, invites, notifications, TLS. |
| [RUNNING_LOCALLY.md](RUNNING_LOCALLY.md) | Running the server and the friends service on their own (also for contributors). |
| [MULTIPLAYER_TEST_PLAN.md](MULTIPLAYER_TEST_PLAN.md) | The cross-network test, step by step. |
| [STRESS_TEST_RESULTS.md](STRESS_TEST_RESULTS.md) | Load numbers for the lobby and relay. |

## Contributors

| Document | What it answers |
|---|---|
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Set-up, running from source, tests, UI conventions, the consent rule, branches and releases. |
| [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | How we treat each other, and how to report a problem. |
| [RUNNING_LOCALLY.md](RUNNING_LOCALLY.md) | `python -m launcher` options, the `lp` command, the data folder, building the exe, resetting permissions, uninstalling. |
| [RELEASE.md](RELEASE.md) | Build, publish and install a release (the GitHub workflow, `install.ps1`, local packaging). |
| [GITHUB_PUSH_CHECKLIST_v1.md](GITHUB_PUSH_CHECKLIST_v1.md) | What goes into a push and what stays out. |
| [CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md) | How releases are signed, and the main-only, tested-before-release rule. |
| [AZURE_SIGNING.md](AZURE_SIGNING.md) | Setting up Azure Artifact Signing for the release workflow (no stored key). |
| [WINDOWS_CHECKLIST.md](WINDOWS_CHECKLIST.md) | What to check by hand on a real Windows computer. |
| [LIBRARY_AND_LAUNCHER_v1.md](LIBRARY_AND_LAUNCHER_v1.md) | The launcher's design note: scanner, library, rooms, waiting lines, server operations. |
| [ROADMAP.md](ROADMAP.md) | Where things stand and what comes next. |
| [.github/PULL_REQUEST_TEMPLATE.md](../.github/PULL_REQUEST_TEMPLATE.md), [.github/ISSUE_TEMPLATE/](../.github/ISSUE_TEMPLATE/bug_report.md) | Pull request checklist and issue forms. |
| [.github/labels.md](../.github/labels.md) | Suggested GitHub labels. |
| [tools/README.md](../tools/README.md) | The tools folder, including the link and UI syntax checks. |
| [tools/ui_archive/README.md](../tools/ui_archive/README.md) | History of how the single-file UI used to be built. |

## Research track

The original plan: Dolphin memory authority, state, events, replay and lockstep sync, with Mario Party 4 first.

| Document | What it answers |
|---|---|
| [PROJECT_SPEC.md](PROJECT_SPEC.md) | Working project specification. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Original architecture overview. |
| [decisions/ADR-0001_STATE_FIRST_EVENT_EXTRACTION.md](decisions/ADR-0001_STATE_FIRST_EVENT_EXTRACTION.md) | Why events are derived from state. |
| [WBS.md](WBS.md) | Work packages and their status (research track, and the launcher track L1–L10). |
| [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) | What "done" means. |
| [EVIDENCE_AND_RECEIPTS.md](EVIDENCE_AND_RECEIPTS.md) | What evidence a claim needs. |
| [REQUIREMENTS_TRACEABILITY.md](REQUIREMENTS_TRACEABILITY.md) | Where each requirement is implemented and tested (research and launcher). |
| [RISK_REGISTER.md](RISK_REGISTER.md) | What can make the project fail. |
| [VERIFICATION_MATRIX_v1.md](VERIFICATION_MATRIX_v1.md) | Automated and live gates. |
| [THREAT_MODEL_v1.md](THREAT_MODEL_v1.md) | The threat model; updated as audit risks close. |
| [IMPLEMENTATION_PLAN_v1.md](IMPLEMENTATION_PLAN_v1.md) | The initial implementation path. |
| [RUNTIME_SPEC_v1.md](RUNTIME_SPEC_v1.md) | Runtime responsibilities. |
| [GAME_PACK_SPEC_v1.md](GAME_PACK_SPEC_v1.md) | What a game pack contains. |
| [ADAPTER_INTERFACE_v1.md](ADAPTER_INTERFACE_v1.md) | The adapter boundary (draft). |
| [WIRE_PROTOCOL_v1.md](WIRE_PROTOCOL_v1.md) | The private coordination protocol. |
| [DOLPHIN_DSU_BACKEND_v1.md](DOLPHIN_DSU_BACKEND_v1.md) | Controller delivery to Dolphin over DSU. |
| [DOLPHIN_FRAME_CONTROL_PROTOCOL_v1.md](DOLPHIN_FRAME_CONTROL_PROTOCOL_v1.md) | Frame-control contract and conformance layer. |
| [DOLPHIN_AUTOCONFIG_v1.md](DOLPHIN_AUTOCONFIG_v1.md) | Dolphin's automatic configuration modes. |
| [FIRST_TARGET_MARIO_PARTY_v1.md](FIRST_TARGET_MARIO_PARTY_v1.md) | Why Mario Party is the first target. |
| [FIRST_ISSUES_AND_MILESTONES_v1.md](FIRST_ISSUES_AND_MILESTONES_v1.md), [FIRST_ISSUES_COPYPASTE_v1.md](FIRST_ISSUES_COPYPASTE_v1.md) | The first milestones and issue texts (historical). |
| [VENTURE_LAB_PITCH.md](VENTURE_LAB_PITCH.md) | The Venture Lab pitch. |
| [adapters/dolphin/README.md](../adapters/dolphin/README.md), [DOLPHIN_PROBE_PLAN_v1.md](../adapters/dolphin/DOLPHIN_PROBE_PLAN_v1.md), [DOLPHIN_RAM_TARGETING_PLAN_v1.md](../adapters/dolphin/DOLPHIN_RAM_TARGETING_PLAN_v1.md), [DOLPHIN_RAM_VALIDATION_v1.md](../adapters/dolphin/DOLPHIN_RAM_VALIDATION_v1.md) | The Dolphin adapter, probe plan, RAM targeting and the all-candidate validation protocol. |
| [tools/memory_probe/README.md](../tools/memory_probe/README.md), [PROBE_SPEC_v1.md](../tools/memory_probe/PROBE_SPEC_v1.md), [memory_reader/README.md](../tools/memory_probe/memory_reader/README.md) | The memory probe. |
| [runtime/README.md](../runtime/README.md) and its parts: [session](../runtime/session/README.md) ([state model](../runtime/session/SESSION_STATE_MODEL_v1.md)), [state](../runtime/state/README.md) ([markers](../runtime/state/STATE_MARKERS_v1.md)), [sync](../runtime/sync/README.md) ([strategy](../runtime/sync/SYNC_STRATEGY_v1.md)), [desync](../runtime/desync/README.md) ([event model](../runtime/desync/DESYNC_EVENT_MODEL_v1.md)), [replay](../runtime/replay/README.md) ([package](../runtime/replay/REPLAY_PACKAGE_v1.md)), [patch](../runtime/patch/README.md) ([coordination](../runtime/patch/PATCH_COORDINATION_v1.md)) | The runtime layers. |
| [game_packs/mario_party_4/README.md](../game_packs/mario_party_4/README.md), [memory discovery](../game_packs/mario_party_4/MEMORY_DISCOVERY_NOTES_v1.md), [phase discovery](../game_packs/mario_party_4/PHASE_DISCOVERY_NOTES_v1.md), [sync model](../game_packs/mario_party_4/MULTIPLAYER_SYNC_MODEL_v1.md) | The Mario Party 4 game pack and its discovery notes. |

### Historical-evidence rule

The following remain valuable but are not current canonical truth unless revalidated against an authoritative
RAM-resolution receipt:

- v1 hot RAM windows;
- action page clusters;
- byte-pattern classifiers;
- absolute memory addresses;
- page-only action labels;
- the former `start_minigame_once` interpretation;
- static RAM candidate rankings.

Do not delete historical evidence. Add a new version with provenance and explain why it supersedes an earlier
interpretation.

## Governance

### Governing order

1. Constellation ecosystem service map, registry, agent policy, and shared invariants (`../Constellation/...`; see
   [the governance-name proposal](proposals/2026-10-10-governance-name.md) for the older "Atlas" name that some
   documents still use).
2. [canonical/ECOSYSTEM_INTEGRATION.md](canonical/ECOSYSTEM_INTEGRATION.md) and `project.contract.json`.
3. Approved repository canonical documents, when added through governance.
4. Working project specification and accepted architecture decisions.
5. WBS, Definition of Done, traceability, risks, and dated audits.
6. Component specifications and historical discovery artifacts.

When documents conflict, the higher item governs. Implementation is evidence of current state, not permission to
redefine the product.

| Document | Status |
|---|---|
| [CLAUDE.md](../CLAUDE.md), [AGENTS.md](../AGENTS.md) | What to read before planning or editing; how canonical changes are proposed. |
| [canonical/ECOSYSTEM_INTEGRATION.md](canonical/ECOSYSTEM_INTEGRATION.md) | Canonical; the service is currently unclassified. |
| [proposals/0001_CLASSIFY_LEGACY_PLAYER.md](proposals/0001_CLASSIFY_LEGACY_PLAYER.md) | The proposed role; not approved. |
| [proposals/0002_UNIFIED_PLAYER_LAUNCHER.md](proposals/0002_UNIFIED_PLAYER_LAUNCHER.md) | The launcher, library and community server; not approved, yet shipping. |
| [proposals/0003_OWNED_EMULATOR_SHELL.md](proposals/0003_OWNED_EMULATOR_SHELL.md), [proposals/0004_FULLY_OWNED_PLAYER.md](proposals/0004_FULLY_OWNED_PLAYER.md) | Engines, installer, open servers, privacy; proposed, first slices built. |
| [proposals/0005_GLOBAL_NETWORK_AND_VOLUNTEER_NODES.md](proposals/0005_GLOBAL_NETWORK_AND_VOLUNTEER_NODES.md) | Volunteer relay nodes; declined by the owner. |
| [proposals/2026-10-07-audit-and-fixes.md](proposals/2026-10-07-audit-and-fixes.md) | October 2026 audit, fixes and follow-ups (problem reports, router opening, player counts, shared-server fallback). |
| [proposals/2026-10-10-governance-name.md](proposals/2026-10-10-governance-name.md) | The ecosystem is named Constellation in the canonical files; older documents say Atlas. |
| [proposals/2026-10-12-launcher-approval-and-canonical-docs.md](proposals/2026-10-12-launcher-approval-and-canonical-docs.md) | The launcher ships while Proposal 0002 is not approved, and `docs/canonical/` lacks IDENTITY, SPEC and CURRENT_STATE: the decision the owner needs to make. |
| [LICENSE](../LICENSE) | MIT. |

## Audits

| Document | Scope |
|---|---|
| [audits/AUDIT_2026-10-12.md](audits/AUDIT_2026-10-12.md) | Re-audit of launcher v0.7.46: friends, TV mode, consent, general health. Its findings are acted on in 0.7.47 ([CHANGELOG.md](../CHANGELOG.md#0747---2026-10-12)). |
| [audits/AUDIT_2026-08-20.md](audits/AUDIT_2026-08-20.md) | Implementation and specification audit of the research track. |
| [proposals/2026-10-07-audit-and-fixes.md](proposals/2026-10-07-audit-and-fixes.md) | The October 2026 audit of the first releases and its fixes. |

## Maintenance rules

- Update traceability and risks in the same change as a requirement or capability status change.
- Add a dated audit rather than rewriting historical audit results.
- Change ecosystem role/ownership only through a proposal and coordinated registry update.
- Update a Definition-of-Done checkbox only when the referenced evidence exists.
- Never use a green unit suite alone as proof of a live emulator, game identity, deterministic replay, or multiplayer
  claim.
- List every new document here, in the group of the people who will read it.
