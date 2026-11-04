# Constellation Ecosystem Agent Policy

## Required behavior

Before modifying a repository under the dev root, an agent must:

1. Read the ecosystem service map and registry.
2. Read the repository's agent instructions and canonical documents.
3. Distinguish current implementation from canonical target state.
4. State the service role and ownership boundary it is working inside.
5. Identify the exact requirement, deficiency, files, tests, and evidence involved.
6. Make bounded changes rather than broad speculative rewrites.
7. Run positive and negative verification.
8. Report unresolved gaps without redefining the product.

## Prohibited behavior

Agents must not:

- Treat absent code as proof that a capability is unnecessary.
- Reduce a deterministic instrument into a generic application.
- Rewrite canonical identity to match incomplete implementation.
- Weaken schemas, trust boundaries, failure semantics, or evidence requirements merely to pass tests.
- Introduce silent fallbacks.
- Present mocked validation as production validation.
- trust stored hashes, counts, signatures, or state without recomputation where verification is required.
- claim release readiness from one successful run.
- introduce hidden cross-repository coupling.
- make a foundational service depend on a higher application layer without an approved architectural decision.

## Change authority

Implementation files may be changed according to project rules.

Canonical identity, service ownership, dependency direction, trust boundaries, and ecosystem role require a proposal and review.

## Where the ecosystem documents are

Every registered repository carries a read-only copy of this policy, the shared invariants, the service map and the registry in its own `.constellation/` folder, so a repository opened on its own still has them. Read those copies; never edit them. They are refreshed from Constellation on every publish.

## Where work is saved

Each repository's files, temporary files and caches stay inside that repository's own folder (for example `.scratch/` or `.work/`), never in the user profile, AppData, the system temp folder or another repository. Paths are resolved relative to the script or repository, never hard-coded to a drive.
