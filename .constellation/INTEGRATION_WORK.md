# Integration work

Open integration work for every service, kept by Constellation and published into every repository as
`.constellation/INTEGRATION_WORK.md`. Find your service's section. Each item names the integration record
(`consumer > provider`, as in `.constellation/integrations.json`), what to build, and how to prove it.

Updated 2026-10-20 from the hand-offs and proposals of Arbiter, Contract Registry, Contribution Ledger, Convergence
Suite, CORE Platform, CorridorWatch, Covenant Courier, Covenant Gate, DoD Witness Kit, DSSE, Echo Transport, HAAI,
HashCanon, InfraBound, LastSignal, LawVM, NFL, SoteriaVault and Veritas Engine (Constellation proposals 0011-0017).

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
   `verify-receipt`). When NFL answers `VERIFIED`, Constellation sets `witnessed`. The owner does this for every
   emitting integration at once with Constellation's "Witness Receipts" button (`cn witness`): it has NFL witness
   each receipt file, verifies every line, and marks only fully verified records `witnessed`. Receipt files are
   found at `proofs/integration_receipts/<consumer>__<provider>/receipts.ndjson` or
   `proofs/receipts/integration/<consumer>__<provider>.ndjson` in the emitter's repository.
5. **Never block on another service.** A missing counterpart is an explicit `unavailable` outcome, never a crash
   or a silent success. Locate other services by parameter, environment variable or config file, never by a
   drive path.

Receipt states as of 2026-10-20: 11 `emitting` (below), none `witnessed` yet, everything else `specified`. `.constellation/integrations.json` always has the current state.

## Decisions that block work (owner)

- `hashcanon > cpr` direction: keep as an optional cross-check, or reverse so CPR consumes HashCanon's law.
- Packet-law ownership: who owns Packet Constitution golden vectors (HashCanon, formal-spec-layer,
  Convergence Suite), and confirmation that PacketId = SHA-256 of the exact on-disk `manifest.json` bytes.
- HashCanon: canonical JSON for every manifest or only content-bound ones; is a packet with no `payload/` valid;
  one manifest contract or two.
- Contribution Ledger weights (all 1 today), and whether rulesets are approved through Arbiter.
- Whether PIE consumes HAAI packets (`pie > haai` has no exchange in code).
- APV <> Veritas Engine direction (who carries whose `result_sha256`); Veritas's trust model and whether it signs
  its verdicts; keep or retire `veritas.ai_assessment.v1`; Veritas proposal 0002 (spec text).
- CORE Platform: direction and contract of the recipe-ledger link (`recipe-ledger.instrument_observation.v1`), and
  DSSE option A (DSSE v1 only for acquisition-scenario stress tests) or B (a DSSE v2 for external engine
  transcripts). Nothing is registered until then.
- LastSignal: whether closing a case requires no `unreviewed` or `disputed` claims; whether to pay for the Windows CI
  job (proposal 0003, about 8-12 minutes per push).
- CovenantWorks: keep the Printers tool in the suite or make it its own service (CovenantWorks proposal 0005).
- Podsteps (not registered): confirm that it may issue OAuth access tokens for its own MCP resource only, or name the
  ecosystem service that should (Podsteps `OAUTH_ECOSYSTEM_NOTE_v1`). Register Podsteps either way.
- CorridorWatch: its ownership was applied from its own proposal 0001 (2026-10-20); confirm or reverse.

---

## aion
- Publish `schemas/` for `ai.artifact.v1`, `ai.execution_trace.v1` and `ai.constitution.bundle.v1` (today only in
  koiosai) and real rule hashes (`verify_aion_constitution_v1.ps1` passes over an empty set); add `proofs/trust/`.
  Veritas pins them (`veritas-engine > aion`, planned).

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

## contract-registry
- `contract-registry > neverlost` is **emitting** (proposal 0017) and has an NFL receipt inbox. Its three receipts
  verified in NFL on 2026-10-19; the Witness Receipts button moves it to `witnessed` once NFL verifies them on this
  computer.
- `contract-registry > atlas-update` was downgraded to `declared`: the references are documentation only.
- `contract-registry > nfl` stays `specified` until anchoring runs (NFL handoff locality conflict).

## contribution-ledger
- `contribution-ledger > watchtower` is **emitting** and has an NFL receipt inbox
  (`proofs/receipts/integration`). No real receipt exists on this computer yet: run the WatchTower adapter once,
  then the Witness Receipts button.
- Run `quick-check` once on Windows PowerShell 5.1. Owner sets the weights before a real ledger.

## core-platform
- Classified from the owner-approved ownership proposal (2026-10-20): physical measurement, TERRA Workbench, RGSR
  fusion over sealed outputs; families `core.measurement`, `core.run_bundle`. No integration is registered.
- Open (owner): recipe-ledger and DSSE links (see Decisions). Housekeeping: recipe-ledger `dashboard/` is
  unversioned and its `origin/main` has unrelated history; `runtime/shadow_profiles` in core-platform, dsse and
  recipe-ledger still hold `C:` paths.

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
- Publish the `covenantgate.effective_policy.v1` format (WatchTower and Contribution Ledger wait on it).
- Hosted evaluator: resolved 2026-10-20 (edge function reproduces every pinned vector). Owner steps left from the
  hosted security fixes: Vercel redeploy, deleting the old functions. Commit the 25 CRLF files as LF.

## corridorwatch
- Classified from its proposal 0001 (families `corridorwatch.ledger_record`, `.project_state`, `.verify_report`,
  `.alert`). Write `docs/canonical/IDENTITY.md`, `SPEC.md` (from `docs/constitution.md`) and `CURRENT_STATE.md`.
- Any email/SMS delivery goes through a registered communications service (Covenant Courier or Rebound) with
  receipts; propose the record first.

## covenant-systems
- Rule on the CanonJSON points Convergence Suite pins as readings 1.1-1.6: key order (UTF-16 or code point),
  trailing LF, escaping, `object_hash`, duplicate keys, `-0`, integers beyond 2^53.

## cpr
- Linux / PowerShell 7 path fix applied by Constellation on 2026-10-20 in `scripts/_lib_cpr_v1.ps1`
  (`Get-RelativePathNormalized` builds absolute URIs with the platform separator; `build_packet_v1.ps1` uses it).
  Commit it and run the CPR selftests on Windows; NFL's test no longer needs its temporary patch.
- Append to `proofs/receipts/cpr.ndjson` instead of rewriting it.
- Reject what HashCanon rejects: hidden unlisted files, `packet_id.txt` with CRLF or trailing spaces, uppercase
  hex, backslash paths.

## dod-witness-kit
- `dod-witness-kit > neverlost` and `dod-witness-kit > relaymesh` (`dodwk.adapter_export.v1`) are **emitting**;
  `dodwk-workbench > dod-witness-kit` (`dodwk.engine_cli.v1`) is **emitting** on the workbench's side. NFL has
  receipt inboxes for all three.
- RelayMesh stays an optional connector, not an upstream service: protection sits above evidence in the layer
  order, so declaring it upstream would break the dependency rule.
- Commit the kit and workbench work (the line-ending fixes come first: 60 files are CRLF where the kit's own rules
  say LF). Remove the root `_audit_*` files or move them under `.scratch/`.
- Constellation's side: the oversight collector now reads every source of a facet, shows `drift_detected` as
  `drift` and `ok: false` as `failed`, and the certification result is an evidence source. Still open: it writes no
  `constellation > dod-witness-kit` receipt for those reads.

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
- `haai > veritas-engine` (planned): map `haai.run_envelope.v1` to `ai.artifact.v1` + trace and reuse the
  `haai > hashcanon` receipt code; packet law stays with APV and HashCanon.

## hashcanon
- `hashcanon > cpr` is **emitting**; its direction is an owner decision.
- Run `FULL_GREEN.cmd` on Windows (real CPR from `..\cpr`), add the PowerShell 7 CI change, run `STATUS.cmd`.
- `watchtower > hashcanon` when WatchTower reads its verify receipts or status file.

## helpcc
- Fix `scripts/helpcc.ps1` (undefined `$runHash`, `$runCanon`, `$createdUtc`), package a run as `ai.artifact.v1`
  + trace and sort keys ordinally; then `helpcc > veritas-engine` (planned): release a governed answer only after
  `veritas-analyze gate` and `veritas-aion check`, with a receipt per call.

## infrabound
- Role and ownership updated for the travel booking hub (InfraBound proposal 0005, owner-approved 2026-10-19):
  families `travel.offer`, `travel.quote`, `travel.order`, `price.observation`, `favorite`. Suppliers (Duffel,
  LiteAPI) are external adapters, not ecosystem services; no integration record is needed for them.

## koiosai
- `koiosai > veritas-engine` (planned): run `veritas-aion check-packet` on each exported packet and write the
  receipt. Seal the output bytes (tier C needs them) or declare tier D; hash real model and runtime bytes, not names.

## lastsignal
- Classified from its proposal 0001 (owner-adopted): evidence model, five evidence laws, case reconstruction and
  packet verification. No integrations, so no receipts yet. Owner: closure criteria and the Windows CI job.

## lawvm
- `lawvm > arbiter` (planned): adopt `arbiter verify` for re-checking decisions.
- Reconcile `schemas/lawvm.receipt.v1.json` with the new receipt schemas and declare which is current.
- `lawvm > neverlost` (planned): signer list and seal-key custody.

## live-state-surgeon
- `live-state-surgeon > hashcanon`: write a receipt for each verifier call (HashCanon answered audit item 6).
- `live-state-surgeon > nfl` is now `declared` only: by its own docs the integrated path is LSS > WatchTower > NFL.
  Write its own receipt when it reads WatchTower's records.
- Move from the dev-only `lss-dev` key to NeverLost-issued device identities.

## neverlost
- Confirm `single-tenant/device_agent/device/<id>` for WatchTower-verified devices (Contribution Ledger).
- Issue principals: Courier nodes (`single-tenant/device_agent/courier/<node-id>`, namespace `courier/message`),
  Covenant Gate's decision signer (namespace `covenant-gate/decision`), Echo's producer (namespace
  `packet/envelope`), LawVM seal signers (NeverLost proposal 0002). Publish the bundle hash out of band.
- Owner: `main` cannot be pushed (build files over 100 MB in its history).
- Merge `audit/constellation-readiness-2026-10-15`. Issue production identities for live-state-surgeon devices and a
  real NFL signing key (NFL still uses the dev key in `proofs/keys`).

## nfl
- Prefer `.constellation/integrations.json` (published) over parsing the service map.
- Receipt inboxes in `config/inbox_registry.json` now cover Courier, Echo, DoD Witness Kit, the workbench, Contract
  Registry and Contribution Ledger. The Witness Receipts button drives `witness-receipt` / `verify-receipt` for
  every emitting record.
- NFL proposal 0002, applied in proposal 0017: family `nfl.ledger` added; `runledger > nfl` carries `nfl.receipt.v1`
  (not RunLedger's own `nfl.receipt.ingested.v1`); the frozen `nfl.tier0.selftest.v1` is off `watchtower > nfl`;
  `live-state-surgeon > nfl` is `declared`. Still open: `global-workbench > nfl` names `nfl.settings.v1`, which NFL
  does not define (Global Workbench owner to say what is meant).
- Packets, not receipts, from WatchTower: ingest only checks them with CPR; record their hashes so WatchTower's
  packets are actually witnessed. Ingest must run from the dev root on any OS, not only `C:\dev` on Windows.

## nfl producers (rebound, runledger, anchormark, ...)
- `nfl.ingest.v1.packet_id` is the producer's declared id only: NFL keys on the CPR-verified packet id and records
  yours as `declared_packet_id`. List `payload/nfl.ingest.json` with its SHA-256 in the manifest, or NFL refuses the
  envelope. Use NFL's `schemas/nfl.ingest.v1.schema.json` as the authoritative copy.

## pie
- `pie > haai` has no exchange in code: build it with a receipt, or say it is not wanted.
- `pie > veritas-engine` (planned): `veritas-aion check-envelope` per signed packet, receipt per call. Veritas found
  that `proofs/runs/pie0`'s signature does not verify: re-sign it, cover `sig_envelope.v1.json` and `signatures/`
  in `sha256sums.txt`, put real keys in `proofs/trust/`, drop the absolute `packet_root`.
- `pie-model`: not registered yet; register it before `pie-model > veritas-engine` can exist.

## rebound
- `rebound > covenant-courier`: replace the bridge's fast-smoke proof with a real `courier.ps1 deliver` call, write
  Rebound's receipt (Courier's hand-off has the exact fields; `scripts/_lib_constellation_integration_receipt_v1.ps1`
  in Courier writes the byte form), pass `-CourierRoot` explicitly (Courier is in `_Covenant-systems`), and run
  Courier on the current PowerShell host.

## soteriavault
- Its four connectors (`> watchtower`, `> neverlost`, `> rebound`, `> recognition`) write receipts; they move to
  `emitting` after a green Windows `update.cmd -Release` with a counterpart inbox configured: send the run's output.
- Registered (proposal 0017): `soteriavault.attestation.v1` on `> watchtower` and `> neverlost`,
  `soteriavault.connector_grant.v1` on `> rebound`; receipts may name them in `carried`.
- NFL is found by the service id `nfl` in `.constellation/integrations.json` and the dev-root layout, never by path.

## veritas-engine
- Veritas's side of every AION record is built and tested; callers write the receipts (fill rules in its
  `docs/HANDOFF.md` section 4).
- Commit the work, run the PowerShell Tier-0 entry point on Windows (appends the receipt ledger) and let CI run.
- Owner decisions: APV <> Veritas direction, trust model and verdict signing, `veritas.ai_assessment.v1`,
  proposal 0002.

## watchtower
- Proven 2026-10-20 (its hand-off): `cn identity` checks and per-project push work. Owner: run
  `RUN_TIER0_GATE.cmd` (or have the branch pushed), and move the old private keys out of `proofs/keys/` (one is
  marked `COMPROMISED`; git does not track them).
- `watchtower > arbiter` (planned): the first real Arbiter caller: build facts at ingest and act on allow, deny or
  quarantine (Arbiter's `examples/watchtower_ingest/`).
- Keep `watchtower.telemetry.receipt.v1` and its chain rules stable, or version them (Contribution Ledger reads
  them).
- If it reads HashCanon's verify receipts or status file: propose `watchtower > hashcanon`.
