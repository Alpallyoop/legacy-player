# .constellation (read-only)

Copies of the Constellation ecosystem's authority documents, so this repository can be read and worked on by itself.
Constellation writes this folder on every `constellation.ps1 publish -Apply`; the authority is Constellation's own registry
and ecosystem documents. Do not edit these files: a change made here is overwritten and is not a change to the ecosystem.
Propose changes in Constellation (`docs/proposals`).

| File | What it is |
|---|---|
| SERVICE_MAP.md | Every service's role, family, ownership boundaries and dependencies |
| registry.json | The registry: families and services (identity, role, owns / does not own, upstream / downstream, contracts) |
| AGENT_POLICY.md | How agents work in any repository of the ecosystem |
| SHARED_INVARIANTS.md | Rules every service keeps |
| REMOTE_WORK.md | Working on this repository from a cloud or phone session, and setting it up for that |
