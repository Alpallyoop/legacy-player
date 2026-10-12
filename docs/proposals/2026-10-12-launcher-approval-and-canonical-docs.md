# Proposal: decide on the launcher, and write the three missing canonical files

**Date:** 2026-10-12
**Status:** Proposal; not approved. It raises a conflict and asks for a decision. It changes no canonical file.
**Decision owners:** the repository owner (Al) and the Constellation ecosystem maintainers.
**Raised by:** the re-audit of v0.7.46 (`docs/audits/AUDIT_2026-10-12.md`, section 4).

## The problem, in plain words

1. **The launcher ships, but the proposal it rests on is not approved.** Legacy Player is released to players as a
   Windows launcher (v0.7.46): a game library, emulator downloads, controllers, saves, a lobby and relay server, server
   codes, a friends service with encrypted messages, TV mode, self-update and an installer. All of this was built under
   `docs/proposals/0002_UNIFIED_PLAYER_LAUNCHER.md`, whose status line still says **"Proposed (not approved; canonical
   files unchanged)"**. Proposals 0003 and 0004 build on 0002 and are also only proposed. Proposal 0001, which would
   classify the service at all, is still "Proposed".
2. **The canonical files do not describe what ships.** `docs/canonical/` holds only `ECOSYSTEM_INTEGRATION.md`. Its
   "This service owns" list says `UNCLASSIFIED` and its "does not own" list says "No ownership boundaries approved
   yet". The canonical role (in that file, `CLAUDE.md`, `AGENTS.md` and `project.contract.json`) is a "compatibility,
   instrumentation, state-understanding, replay-verification, and multiplayer-orchestration runtime". A consumer
   launcher with a library, downloads, a friends service and self-update is not in that sentence.
3. **`IDENTITY.md`, `SPEC.md` and `CURRENT_STATE.md` do not exist.** `CLAUDE.md` tells every agent to read them "when
   present". Because they are missing, agents fall back on the code and on working documents, which `CLAUDE.md` says
   not to do ("Do not infer the entire product from implementation alone").
4. **Shipped features go past what 0002 proposed.** 0002 says public matchmaking, accounts and internet-scale abuse
   prevention stay "not owned". The friends service now has friend codes, presence, reports, bans, a word filter and a
   moderation console. Self-update, PC (Steam/Epic) games, TV mode and the problem-report receiver are not mentioned in
   0002 at all.

Nothing in this change resolves these points. Code, canonical files, the registry and `project.contract.json` stay as
they are.

## The decision the owner needs to make

Pick one:

- **A. Approve the launcher as part of `legacy-player`.** Approve 0001 and 0002 (with an amendment listing the extra
  shipped features in point 4), widen the canonical role to name the launcher, fill in the owned and not-owned lists,
  and write the three files below. The registry entry in Constellation and `project.contract.json` change with it,
  following the change-governance steps in `docs/canonical/ECOSYSTEM_INTEGRATION.md`.
- **B. Split the launcher into its own service.** Keep `legacy-player` as the research runtime described today and
  register the launcher (and perhaps the friends service) as separate services that depend on it. This needs a new
  repository or a clearly separated folder, and a migration plan.
- **C. Keep the launcher as an experiment.** Leave the role as it is, label releases as experimental, and stop adding
  launcher features until A or B is chosen.

Questions that come with any choice:

1. Is the friends service (codes, presence, moderation) owned here, owned by another Constellation service, or a
   non-goal that should be removed?
2. Is self-update (the app replacing itself from GitHub releases) an accepted responsibility?
3. Which trust boundary holds for the host's address? The owner wants it kept secret; today's server code carries it
   (audit 3.5). This belongs in the spec once decided.
4. Do the consent rules (player agrees before every network contact, download, system change or data share) become a
   canonical invariant? The audit found them only partly enforced.

## Draft outlines for the three missing files

These are outlines only, for the owner to fill in after the decision. They are not canonical until approved.

### `docs/canonical/IDENTITY.md`

- What Legacy Player is, in one paragraph (after the decision above).
- Who it is for: players on their own PCs; the owner and friends first.
- Owned responsibilities (each one line), for example: local game library (read-only), emulator integration through
  adapters, controller and save management, private-group hosting (rooms, relay, server codes), and, if approved, the
  friends service and self-update.
- Not owned (non-goals): emulator implementation, distributing games or BIOS, public matchmaking, player accounts, any
  required rented server.
- Core principles: local-first; the player's consent before acting; the host's address kept private; no game content
  shipped; standalone-first.
- Relationship to the research track (memory authority, replay, lockstep) and to Constellation.

### `docs/canonical/SPEC.md`

- Scope and the two tracks (launcher, research), with which requirement IDs belong to each (LP-LR and LP-FR/LP-NFR).
- Trust boundaries: the local web UI (loopback, per-run token), the lobby and relay server, the friends service, the
  release download path.
- Public schemas and contracts: wire protocol (`docs/WIRE_PROTOCOL_v1.md`), server-code format, friends API, game-pack
  and adapter specs, settings schema (`launcher/catalog.py`).
- Consent rules: what needs a yes, how the yes is recorded (time, policy version), and how it is withdrawn.
- Release criteria: tested commit, hashes, attestation, signing policy, rollback.
- Deterministic behaviour that must hold (replay, state hashes) for the research track.

### `docs/canonical/CURRENT_STATE.md`

- Current version and date, and how to verify it (test count, release workflow run).
- What works and how it is evidenced (pointing at the L1–L10 rows in `docs/WBS.md` and LP-LR rows in
  `docs/REQUIREMENTS_TRACEABILITY.md`).
- What is not proven (real Windows hardware, two-network play, friends across networks).
- Open audit findings and their owners (`docs/audits/AUDIT_2026-10-12.md`).
- Known conflicts between code and canonical text (starting with this proposal), so agents report them instead of
  guessing.

## Compatibility impact

None from this proposal: it only documents the conflict and asks for a decision. Choice A or B changes the service role,
ownership lists, registry entry and `project.contract.json`, and must go through the change-governance steps in
`docs/canonical/ECOSYSTEM_INTEGRATION.md`. Choice C may require the launcher to be labelled experimental in
`README.md` and release notes.

## What changed alongside this proposal

Working documents only: `docs/ROADMAP.md`, `docs/WBS.md` (launcher work packages L1–L10),
`docs/REQUIREMENTS_TRACEABILITY.md` (LP-LR rows), `docs/PROJECT_SPEC.md` (scope note) and
`docs/LIBRARY_AND_LAUNCHER_v1.md` now say which track they cover and point here. They describe what ships; they do not
approve it.
