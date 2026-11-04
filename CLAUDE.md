# Claude Code Instructions — legacy-player

<!-- ATLAS_SERVICE_MAP_BEGIN -->
## Constellation ecosystem context

This repository is the `legacy-player` service inside the Constellation deterministic software ecosystem.

**Canonical role:** Local-first compatibility, instrumentation, state-understanding, replay-verification, and multiplayer-orchestration runtime for legacy games; integrates emulators through adapters and games through versioned game packs.

**Ecosystem authority:** Constellation (`constellation`). The registry, service map, agent policy and shared invariants below are published by Constellation.

Before auditing, planning, refactoring, or editing this repository, read:

1. `.constellation/SERVICE_MAP.md`
2. `.constellation/registry.json`
3. `.constellation/AGENT_POLICY.md`
4. `.constellation/SHARED_INVARIANTS.md`
5. `docs\canonical\ECOSYSTEM_INTEGRATION.md`
6. `docs\canonical\IDENTITY.md` when present
7. `docs\canonical\SPEC.md` when present
8. `docs\canonical\CURRENT_STATE.md` when present
9. `project.contract.json` when present

Items 1-4 are read-only copies kept in `.constellation/` so this repository can be read on its own; Constellation refreshes them on every publish. The authority itself is Constellation's registry and ecosystem documents. Never edit the copies; propose changes to Constellation.

Working on this repository away from the owner's computer (cloud or phone session), or asked to set it up for that: read `.constellation/REMOTE_WORK.md` first.

Integrating with another service, or asked what integration work is open: read this service's section of `.constellation/INTEGRATION_WORK.md`. Every exchange writes a receipt (`.constellation/constellation.integration.receipt.v1.json`); the registered integrations are in `.constellation/integrations.json`.

Do not infer the entire product from implementation alone. Current code can be incomplete, transitional, or incorrect.

Do not silently redefine:

- the service role,
- owned responsibilities,
- non-goals,
- dependency direction,
- trust boundaries,
- public schemas,
- receipt contracts,
- deterministic behavior,
- or release criteria.

When code and canonical documents conflict, report the conflict before choosing behavior.

Ordinary implementation work must not directly weaken canonical files. Put proposed canonical changes under `docs\proposals`.
<!-- ATLAS_SERVICE_MAP_END -->
