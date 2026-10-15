# Integration work

Open integration work for every service, kept by Constellation and published into every repository as
`.constellation/INTEGRATION_WORK.md`. Find your service's section. Each item names the integration record
(`consumer > provider`, as in `.constellation/integrations.json`), what to build, and how to prove it.

Updated 2026-10-15 from the hand-offs of Arbiter, Contribution Ledger, Convergence Suite, Covenant Courier, DoD Witness
Kit, DSSE, Echo Transport, HAAI, HashCanon, LawVM and NFL (Constellation proposals 0011-0015).

## How an integration is done

1. **Use the registered contract.** If the record you need is not in `.constellation/integrations.json`, propose
   it in your `docs/proposals/` first; NFL refuses receipts of unregistered integrations (`RECEIPT_UNATTRIBUTED`).
2. **Write a receipt for every exchange you start**, including refused, unavailable and failed ones:
   `constellation.integration.receipt.v1` (schema: `.constellation/constellation.integration.receipt.v1.json`).
   One line per exchange, keys in schema order, no timestamps, `prev_sha256` chain per integration, written
   locally first. Copy the schema byte for byte if you validate against it; it is the authority.
3. **Prove it**: a positive test (receipt written and verifies) and a negative test (a failed exchange still
   writes a receipt with an error token). Then ask Constellation to set the record's receipt `state` to
   `emitting`.
4. **Get it witnessed**: hand the receipts to NFL (an NFL inbox in `receipt` mode, or NFL's `witness` /
   `verify-receipt`). When NFL answers `VERIFIED`, Constellation sets `witnessed`.
5. **Never block on another service.** A missing counterpart is an explicit `unavailable` outcome, never a crash
   or a silent success. Locate other services by parameter, environment variable or config file, never by a
   drive path.

Receipt states today: 7 `emitting` (below), none `witnessed`, everything else `specified`.

## Decisions that block work (owner)

- `hashcanon > cpr` direction: keep as an optional cross-check, or reverse so CPR consumes HashCanon's law.
- Packet-law ownership: who owns Packet Constitution golden vectors (HashCanon, formal-spec-layer,
  Convergence Suite), and confirmation that PacketId = SHA-256 of the exact on-disk `manifest.json` bytes.
- HashCanon: canonical JSON for every manifest or only content-bound ones; is a packet with no `payload/` valid;
  one manifest contract or two.
- Contribution Ledger weights (all 1 today), and whether rulesets are approved through Arbiter.
- Whether PIE consumes HAAI packets (`pie > haai` has no exchange in code).

---

## apv
- Candidate `apv > haai` (from HAAI): APV re-verifies HAAI packets (`haai.run_envelope.v1`,
  `hashcanon.manifest.v1`) and writes its own receipts. Needs a registry proposal first.
- Candidate adopter of Convergence Suite's packet vectors.

## arbiter
- **New role (owner, 2026-10-15): Covenant Gate's re-verifier.** Covenant Gate decides first, then hands Arbiter
  the decision with the exact policy and facts it used. Arbiter re-evaluates independently and classifies the
  original decision. Define `policy.reverification.v1` (for example: the original decision's hash, Arbiter's own
  decision and hash, and a classification such as match / mismatch with both outcomes) and the command that
  produces it. Arbiter never enforces or overrides; Covenant Gate decides what a mismatch means.
- `watchtower > arbiter`, `lawvm > arbiter` (planned): Arbiter's half is done; support the callers.
- Decide whether `arbiter.receipt.v1` stays (with a published schema) or is dropped in favour of LawVM's record.
- Open in Arbiter's own repository: `effective_from` / `expires_at` / `trust_requirements`, signing, schema id base
  URL, integers in schemas, folding proposal 0001 into SPEC.

## assemblelink
- `assemblelink > echo-transport` (contracts `echo.transport.cli.v1`, `echo.receipt.v2`): write the receipt for
  each Echo call.
- Take back the removable-media slice that lives in `echo-transport` (`toolbelt/`, `ASSEMBLELINK_*` docs,
  `_RUN_dev_*` scripts) and call `echo_transport_v1.ps1 ingest` instead (Echo proposal 0001 section 3). Its docs
  name `_RUN_vader_*` scripts that do not exist.

## contribution-ledger
- `contribution-ledger > watchtower` is **emitting**. After the next publish, run `witness -NflRoot ..\nfl`, then
  NFL's `verify-receipt`; on `VERIFIED`, ask Constellation for `witnessed`.
- Run `quick-check` once on Windows PowerShell 5.1. Owner sets the weights before a real ledger.

## convergence-suite
- Merge `cs-v1.1-buildout`, tag `cs-freeze-v1.1`, run `verify-freeze` on a clean checkout of the tag.
- Install the kit in the first adopter (HashCanon is the natural first; others: formal-spec-layer, cpr, apv,
  traceglass, live-state-surgeon, claim-protocol, anchormark). Each adopter gets `<adopter> > convergence-suite`
  when it commits its first run.
- Send the CanonJSON questions to covenant-systems and the vector-ownership question to formal-spec-layer and
  HashCanon (Convergence Suite proposal 0002).

## covenant-courier
- `covenant-courier > covenant-gate` and `covenant-courier > neverlost` are **emitting**.
- Merge `claude/courier-governed-delivery` after a Windows `courier.ps1 verify-all`.
- Later: deliver over VTP v2 sessions, in-session DH ratchet, NeverLost-issued signers, a new release bundle.

## covenant-gate
- **`covenant-gate > arbiter` (owner, 2026-10-15): re-verification.** After each decision, hand Arbiter the
  `policy.decision.v1` with the exact policyset and input, keep Arbiter's `policy.reverification.v1`, decide what a
  mismatch means for enforcement, and write a receipt carrying both hashes.
- For Courier: a base-policy rule for `enforcement_point: eval.request`, `action.type: courier.deliver` (today
  every Courier delivery is `DEFAULT_DENY`); signed decision documents (`ssh-keygen -Y sign`, namespace
  `covenant-gate/decision`, by a NeverLost principal); keep `CG-CanonBytes` and the `evaluation_id` formula stable.
- For LawVM: export each decision's output, base policy, overlay and input in the `cases/` + `expected/` layout;
  compare case-sensitively and sort ordinally.
- Through Covenant Gate's own change control (its hook protects these paths).

## covenant-systems
- Rule on the CanonJSON points Convergence Suite pins as readings 1.1-1.6: key order (UTF-16 or code point),
  trailing LF, escaping, `object_hash`, duplicate keys, `-0`, integers beyond 2^53.

## cpr
- Run on PowerShell 7 and Linux: `[System.Uri]` built from a relative path fails off Windows (NFL proposal 0002
  section 7 has the two-line fix; `build_packet_v1.ps1` has the same failure).
- Append to `proofs/receipts/cpr.ndjson` instead of rewriting it.
- Reject what HashCanon rejects: hidden unlisted files, `packet_id.txt` with CRLF or trailing spaces, uppercase
  hex, backslash paths.

## dod-witness-kit
- Its README names `docs/proposals/0001-constellation-integration-alignment.md`, which is not in the repository
  yet: write it, with the receipt state each integration has reached.
- `constellation > dod-witness-kit` (owner-declared): Constellation reads `dodwk.drift_report.v2` and
  `dodwk.certification_verification_result.v1` (`docs/SPEC_CONSTELLATION_EVIDENCE_V1.md`). Confirm both are the
  contracts on that record.
- `dod-witness-kit > neverlost` (`neverlost.trust_bundle.v1`) and `dod-witness-kit > relaymesh`
  (`dodwk.adapter_export.v1`, proposed id): it writes integration receipts (`docs/RECEIPTS.md`); say which have
  positive and negative tests so Constellation can set them to `emitting`.
- `relaymesh > dod-witness-kit` is also recorded: say whether RelayMesh really calls the kit or the record is the
  same link seen from the other side.
- Untracked `_audit_*` files and folders at the repository root (`_audit_cn.tgz`, `_audit_src.tgz`,
  `_audit_eco/`, `_audit_oversight.mjs`): remove them or move them under `.scratch/`, so a backup does not commit
  them. The last backup did not commit this repository's 132 changes; the next backup reports why.

## dsse
- No integrations. Write `docs/canonical/IDENTITY.md`, `SPEC.md` (from `docs/DSSE_V1.md`) and `CURRENT_STATE.md`.

## echo-transport
- `echo-transport > nfl` and `echo-transport > neverlost` are **emitting**.
- Commit the 1.1.0 work (only the README is on GitHub). Owner: rotate the Covenant Gate Supabase keys found in
  `toolbelt/` and the unencrypted producer key.
- After NeverLost issues a signer list with the `packet/envelope` namespace for Echo, `trust-import` it.

## formal-spec-layer
- Reconcile the written PacketId law with every working tool (SHA-256 of the on-disk `manifest.json` bytes),
  fix the miscomputed golden vector, and define how packets are signed (Echo Transport proposal 0002).
- Settle golden-vector ownership with HashCanon and Convergence Suite.

## global-workbench
- `global-workbench > covenant-courier` (planned): add `workbench-plugins/covenant-courier/plugin.manifest.json`
  (draft in Courier proposal 0001 section 6) and define `covenant_courier.settings.v1`.
- Say what `nfl.settings.v1` on `global-workbench > nfl` means; NFL has no settings contract.

## haai
- `haai > hashcanon` is **emitting**. Hand its receipts to NFL (drop them in NFL's `inbox/receipts`, or ask NFL for
  an inbox entry), then ask for `witnessed`.

## hashcanon
- `hashcanon > cpr` is **emitting**; its direction is an owner decision.
- Run `FULL_GREEN.cmd` on Windows (real CPR from `..\cpr`), add the PowerShell 7 CI change, run `STATUS.cmd`.
- `watchtower > hashcanon` when WatchTower reads its verify receipts or status file.

## lawvm
- `lawvm > arbiter` (planned): adopt `arbiter verify` for re-checking decisions.
- Reconcile `schemas/lawvm.receipt.v1.json` with the new receipt schemas and declare which is current.
- `lawvm > neverlost` (planned): signer list and seal-key custody.

## live-state-surgeon
- `live-state-surgeon > hashcanon`: write a receipt for each verifier call (HashCanon answered audit item 6).

## neverlost
- Confirm `single-tenant/device_agent/device/<id>` for WatchTower-verified devices (Contribution Ledger).
- Issue principals: Courier nodes (`single-tenant/device_agent/courier/<node-id>`, namespace `courier/message`),
  Covenant Gate's decision signer (namespace `covenant-gate/decision`), Echo's producer (namespace
  `packet/envelope`), LawVM seal signers (NeverLost proposal 0002). Publish the bundle hash out of band.
- Owner: `main` cannot be pushed (build files over 100 MB in its history).

## nfl
- Prefer `.constellation/integrations.json` (published from now on) over parsing the service map.
- Receipt inboxes for Courier (`covenant-courier>covenant-gate`, `covenant-courier>neverlost`) and Echo's NFL
  outbox are added to `config/inbox_registry.json`; ingest them after the next publish.
- Witness the 7 emitting integrations as their receipts arrive; answer `verify-receipt` so records move to
  `witnessed`. Remaining registry items: NFL proposal 0002.

## pie
- `pie > haai` has no exchange in code: build it with a receipt, or say it is not wanted.

## rebound
- `rebound > covenant-courier`: replace the bridge's fast-smoke proof with a real `courier.ps1 deliver` call, write
  Rebound's receipt (Courier's hand-off has the exact fields; `scripts/_lib_constellation_integration_receipt_v1.ps1`
  in Courier writes the byte form), pass `-CourierRoot` explicitly (Courier is in `_Covenant-systems`), and run
  Courier on the current PowerShell host.

## watchtower
- `watchtower > arbiter` (planned): the first real Arbiter caller: build facts at ingest and act on allow, deny or
  quarantine (Arbiter's `examples/watchtower_ingest/`).
- Keep `watchtower.telemetry.receipt.v1` and its chain rules stable, or version them (Contribution Ledger reads
  them).
- If it reads HashCanon's verify receipts or status file: propose `watchtower > hashcanon`.
