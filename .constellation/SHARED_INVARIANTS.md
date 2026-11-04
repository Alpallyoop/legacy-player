# Constellation Shared Determinism and Evidence Invariants

These are baseline rules. Individual projects may impose stricter requirements.

- Canonical text artifacts use UTF-8 without BOM and LF line endings.
- Canonical object and directory ordering is stable and explicit.
- SHA-256 is the default content hash unless a project contract explicitly defines another algorithm.
- Hashes are calculated over precisely defined canonical bytes.
- Floating-point values are forbidden in canonical JSON unless a deterministic representation is explicitly specified.
- Timestamps, random identifiers, machine paths, usernames, and environment-specific values must not contaminate reproducible content unless isolated as noncanonical metadata.
- Stored hashes, signatures, counts, and state claims are independently recomputed by verifiers.
- Missing dependencies, malformed inputs, invalid signatures, stale state, and verification failures fail closed.
- Success tokens are emitted only after outputs are durably written and verified.
- Append-only evidence must not be rewritten in place.
- Tests include valid, invalid, corrupted, partial, replayed, stale, and clean-state cases appropriate to the instrument.
- Existing green behavior must not be weakened during refactoring.
- Integration boundaries use versioned contracts rather than undocumented shared assumptions.
- Every registered integration writes a receipt for every exchange, including failed ones (`constellation.integration.receipt.v1`, proposal 0013): locally first, then its hash is witnessed by NFL. Witnessing never blocks the integration, and a witness only commits hashes that belong to a registered integration.
- A model explanation is not proof.
