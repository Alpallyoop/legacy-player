# Integration work

Open integration work for every service, kept by Constellation and published into every repository as
`.constellation/INTEGRATION_WORK.md`. Find your service's section. Each item names the integration record
(`consumer > provider`, as in `.constellation/integrations.json`), what to build, and how to prove it.

Updated 2026-10-20 from the hand-offs and proposals of Arbiter, Contract Registry, Contribution Ledger, Convergence
Suite, CORE Platform, CorridorWatch, Covenant Courier, Covenant Gate, DoD Witness Kit, DSSE, Echo Transport, HAAI,
HashCanon, InfraBound, LastSignal, LawVM, NFL, SoteriaVault and Veritas Engine (Constellation proposals 0011-0017),
Observatory, BountyGate and ThemeForge (0019-0022), CSL, TRIAD, Rebound, Covenant Gate and CORE Platform
(0023, 2026-10-21), and DoD Witness Kit's second audit (0027, 2026-10-21).

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

Receipt states as of 2026-10-22: 21 `emitting` (below), 3 `witnessed` (`contract-registry > neverlost`, `csl > cpr`, `global-workbench > themeforge`), everything else `specified`. `.constellation/integrations.json` always has the current state.

## Decisions that block work (owner)

- `hashcanon > cpr` direction: keep as an optional cross-check, or reverse so CPR consumes HashCanon's law.
- HashCanon: canonical JSON for every manifest or only content-bound ones; is a packet with no `payload/` valid;
  one manifest contract or two.
- Contribution Ledger weights (all 1 today), and whether rulesets are approved through Arbiter.
- APV <> Veritas Engine direction (who carries whose `result_sha256`); Veritas's trust model and whether it signs
  its verdicts; keep or retire `veritas.ai_assessment.v1`; Veritas proposal 0002 (spec text).
- CORE Platform: direction and contract of the recipe-ledger link (`recipe-ledger.instrument_observation.v1`), and
  DSSE option A (DSSE v1 only for acquisition-scenario stress tests) or B (a DSSE v2 for external engine
  transcripts). Nothing is registered until then.
- LastSignal: whether closing a case requires no `unreviewed` or `disputed` claims; whether to pay for the Windows CI
  job (proposal 0003, about 8-12 minutes per push).
- CovenantWorks: keep the Printers tool in the suite or make it its own service (CovenantWorks proposal 0005).
- TRIAD: the content-only capture manifest v3 (`TRIAD_CAPTURE_MANIFEST_V3_CONTENT_IDENTITY`).
- CorridorWatch: its ownership was applied from its own proposal 0001 (2026-10-20); confirm or reverse.

## Decided by the owner (2026-10-21, proposal 0025)

- **Packet law.** PacketId = SHA-256 of the exact on-disk `manifest.json` bytes (HashCanon's and CPR's rule).
  `sha256sums.txt` lines are `<hex>  <rel>` (two spaces). HashCanon's golden vectors are authoritative; CSL's become a
  conformance mirror: CSL adds a v2 vector set under the on-disk rule and keeps the v1 set as frozen evidence.
  CanonJson rejects `-0` and lone surrogates (fail closed, like every other non-canonical input).
- **Rebound scope: option A.** The role covers the hosted mail product (accounts, organizations, billing, portal,
  templates, calendar sync, linked accounts, integrations). Sessions: the platform owner's never expire by design;
  admins' session lengths are set by their supervisors (organization owners) or by the platform owner.
- **Covenant Gate.** Add the narrow rule `allow.courier.deliver.human` (human-originated Courier deliveries allowed;
  AI-originated stay default-deny), through change control with positive and negative vectors. An Arbiter mismatch
  never loosens a decision: if Covenant Gate allowed and Arbiter would not, the action goes to `review`; a deny stays
  a deny; every mismatch is recorded in the receipt.
- **Podsteps (`proteusops`)** may issue delegated OAuth access tokens for its own MCP resource only; it is not an
  identity provider for other services.
- **Observatory > HashCanon** is a registered integration (verifier conformance call; Observatory writes receipts).
- **Rebound organization addresses:** on a customer organization's verified domain, owners and admins create
  addresses; members can request one, which an owner or admin approves. Make `OrgDomains.cs`, `BusinessAccounts.cs` and
  `PortalService.ResolveVerifiedDomainAsync` agree, with positive and negative tests (member request, approval,
  refusal; a member cannot create directly).
- **Rebound and NFL:** `LAW.md`'s "every pledge event to NFL" covers only the governance and packet pipeline
  (`scripts/`), never the hosted service: per-event witnessing would clog the mail infrastructure. `rebound > nfl`
  stays `declared`; scope `LAW.md` to say so.
- **Covenant Gate licences count machines:** activation counting is wanted. It must never make the gate fail open: an
  expired or over-limit licence stops new activations, not the safety rules already running on a machine.
- **CovenantWorks script fonts** (CJK, Devanagari, Arabic with shaping, right-to-left) for PDF export of translated
  documents: done in CovenantWorks 0.3.0 (proposal 0007). It shipped as the overlay pack
  `fontpack_v2_suite+scripts_v1` (pinned Noto faces downloaded on request), not as `fontpack_v3`, so existing layout
  and PDFs are unchanged (byte-identical template test); new vectors are pinned in `test_vectors/suite_scripts_v1`.
- **TRIAD signs restore attestations by default** (with a NeverLost-issued key); unsigned only when signing is
  unavailable, and then the attestation says so.

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

## bountygate
- `bountygate > nfl` (`nfl.ledger.record.v1`), `bountygate > arbiter` (`policy.input.v1`, `policy.decision.v1`,
  carried) and `bountygate > neverlost` (`neverlost.allowed_signers.make.v1`, `neverlost.sig.verify.v1`) are
  **emitting** (proposal 0020). All three are optional; a missing counterpart is an `unavailable` receipt.
  Receipts: `proofs/integration_receipts/bountygate__<provider>/receipts.ndjson`.
- Arbiter evaluates BountyGate's own PolicySet (`integrations/arbiter/`) for every active-tool plan BountyGate
  allows; it can only tighten (deny / quarantine block the plan; exit 1 counts as deny).
- NeverLost (owner): issue BountyGate a principal and key with namespace `bountygate/export` and export its
  `allowed_signers`; until then signing reports `unavailable`.
- Owner, home computer: set `config/integrations.local.json` (NFL and Arbiter folders, NeverLost files), produce
  real receipts, then "Witness Receipts" to reach `witnessed`. Run `scripts/bg_selftest_all_v1.ps1` and
  `npm run test:all` on Windows PowerShell 5.1 once (only PowerShell 7 was exercised).

## contract-registry
- NeverLost asks: stop writing machine output into other repositories' `runtime/` folders (shadow profiles).
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
- Optional: adopt FSL's law-conformance set as a source of cross-instrument packet vectors (no change required).
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
- Owner decisions (proposal 0025): add `allow.courier.deliver.human` to the base policy through change control (vectors:
  human delivery allowed; AI delivery and other action types still default-deny). For Arbiter re-verification, a
  mismatch moves an allow to `review`, never loosens a deny, and is recorded in the `covenant-gate > arbiter` receipt;
  then switch the bridge on.
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
- For Observatory (proposal 0019): keep `scripts/cg_eval_cli_v1.ps1` (`-BasePolicyPath -InputPath -OutPath`), the
  `covenantgate.eval_output.v1` fields and the `evaluation_id` formula stable; a change to the effective-policy
  derivation changes Observatory's pinned policy hash and blocks its AI admissions until re-pinned.
- Installer-only since 2026-10-20 (owner): hosted evaluation is retired (410 Gone); gi-ppi.com sells licences and
  serves the installer. No registered integration used the hosted endpoint. Owner items: licence signing key, first
  installer, EULA review, retire the legacy mint functions.
- `covenant-gate > neverlost` is **emitting** (`neverlost.trust_bundle.v1`, proposal 0023). Its receipts are written
  under the gate's data root (`integration/receipts/`), not in the repository, so the Witness Receipts button does
  not find them: switch on the gate's own best-effort NFL witnessing (`witness.enabled` + the NFL CLI path).
- `covenant-gate > nfl` witnessing and LawVM evidence are built; run LawVM `monitor` once on Windows.

## corridorwatch
- Classified from its proposal 0001 (families `corridorwatch.ledger_record`, `.project_state`, `.verify_report`,
  `.alert`). Write `docs/canonical/IDENTITY.md`, `SPEC.md` (from `docs/constitution.md`) and `CURRENT_STATE.md`.
- Any email/SMS delivery goes through a registered communications service (Covenant Courier or Rebound) with
  receipts; propose the record first.

## covenant-systems
- Rule on the CanonJSON points Convergence Suite pins as readings 1.1-1.6: key order (UTF-16 or code point),
  trailing LF, escaping, `object_hash`, duplicate keys, `-0`, integers beyond 2^53.

## cpr
- From FSL proposal 0002: sort `sha256sums.txt` ordinally in the builder (it uses culture order today); writing canonical
  manifests is recommended, not required.
- Linux / PowerShell 7 path fix applied by Constellation on 2026-10-20 in `scripts/_lib_cpr_v1.ps1`
  (`Get-RelativePathNormalized` builds absolute URIs with the platform separator; `build_packet_v1.ps1` uses it).
  Commit it and run the CPR selftests on Windows; NFL's test no longer needs its temporary patch.
- Append to `proofs/receipts/cpr.ndjson` instead of rewriting it.
- Reject what HashCanon rejects: hidden unlisted files, `packet_id.txt` with CRLF or trailing spaces, uppercase
  hex, backslash paths.

## csl
- FSL's P07-P09 and N54-N56 pin exactly the on-disk vs canonical difference; mirror them in the v2 set.
- Packet law decided (see above): add the v2 vector set under the on-disk PacketId rule and `<hex>  <rel>` sums; reject
  `-0` and lone surrogates in CanonJson, with vectors.
- Classified (proposal 0023): CanonJson / HashLaw / Packet Constitution conformance vectors, the
  `csl.nfl.packet.manifest.v1` contract and CSL's evidence formats; families `csl`, `pcv1`.
- `csl > cpr` is **emitting** and has an NFL receipt inbox (`proofs/integration_receipts/csl__cpr/`).
- Open law points are in Decisions (PacketId rule, sums line form, golden-vector ownership, CanonJson `-0` and lone
  surrogates). CSL adds a v2 vector set once they are ruled; the v1 set stays frozen.

## dod-witness-kit
- `dod-witness-kit > neverlost` and `dod-witness-kit > relaymesh` (`dodwk.adapter_export.v1`) are **emitting**;
  `dodwk-workbench > dod-witness-kit` (`dodwk.engine_cli.v1`) is **emitting** on the workbench's side. NFL has
  receipt inboxes for all three.
- RelayMesh stays an optional connector, not an upstream service: protection sits above evidence in the layer
  order, so declaring it upstream would break the dependency rule.
- Done 2026-10-21 (second audit, proposal 0027): all five owned capabilities built and tested (signed
  certification, architecture maps bound to certification, run receipts `dodwk.certification_receipt.v1`), the kit
  certifies itself, line endings fixed (LF; `.cmd` CRLF), root scratch moved out, historical `release/cli` and
  `scripts/_patch` removed. Open on the kit: one run of the full tests on Windows PowerShell 5.1.
- Constellation's side: the oversight collector reads every source of a facet, shows `drift_detected` as `drift`
  and `ok: false` as `failed`, and the certification result is an evidence source. Still open: write the
  `constellation > dod-witness-kit` receipt for those reads (carry the drift report's `canonical_sha256`), and
  regenerate the kit's `docs/canonical/ECOSYSTEM_INTEGRATION.md` (it still says "Owns: UNCLASSIFIED").

## dsse
- No integrations. Write `docs/canonical/IDENTITY.md`, `SPEC.md` (from `docs/DSSE_V1.md`) and `CURRENT_STATE.md`.

## echo-transport
- From FSL proposal 0002: pin the SSHSIG form: reject a non-empty `reserved` field, non-sha512, non-Ed25519 and
  non-canonical armor (FSL check 18 step 3; vectors N72, N73 show unsigned bytes riding along today); require
  `signing_principal` and `signature_namespace` in the manifest instead of trying every principal in `allowed_signers`
  (FSL rejects `SIGNATURE_UNDECLARED`).
- `echo-transport > nfl` and `echo-transport > neverlost` are **emitting**.
- Commit the 1.1.0 work (only the README is on GitHub). Owner: rotate the Covenant Gate Supabase keys found in
  `toolbelt/` and the unencrypted producer key.
- After NeverLost issues a signer list with the `packet/envelope` namespace for Echo, `trust-import` it.

## formal-spec-layer
- Done 2026-10-21 (FSL proposal 0001): law reconciled to the on-disk PacketId rule, golden vector rebuilt
  (`19bc3d8d...`; anything pinning `d005ce38...` moves), HashCanon's vectors carried as P10-P13, signature profile in
  `docs/SIGNATURES.md`. Classified in proposal 0028. A service conforms when its verifier gives FSL's expected outcome for
  every case in `test_vectors/vectors.index.ndjson`.

## global-workbench
- `global-workbench > covenant-courier` (planned): add `workbench-plugins/covenant-courier/plugin.manifest.json`
  (draft in Courier proposal 0001 section 6) and define `covenant_courier.settings.v1`.
- Say what `nfl.settings.v1` on `global-workbench > nfl` means; NFL has no settings contract.
- `global-workbench > themeforge` is **emitting** (proposal 0021; Global Workbench proposal 0001): ThemeForge plugin and
  `workbench-core/electron/themeforge-engine.cjs`; receipts in `proofs/integration_receipts/global-workbench__themeforge/`.

## haai
- `haai > hashcanon` is **emitting**. Hand its receipts to NFL (drop them in NFL's `inbox/receipts`, or ask NFL for
  an inbox entry), then ask for `witnessed`.
- `haai > veritas-engine` (planned): map `haai.run_envelope.v1` to `ai.artifact.v1` + trace and reuse the
  `haai > hashcanon` receipt code; packet law stays with APV and HashCanon.

## hashcanon
- From FSL proposal 0002 (proposal 0028): exempt exactly `signatures/sha256sums.sig` from sums coverage under the FSL
  signature profile (a seal over `sha256sums.txt` cannot cover itself); enforce `payload/**` (at least one file, as your
  spec section 3 says); reject `-0` and lone surrogates (proposal 0025). Then run FSL's vector set against your verifier.
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
- For packet signers (FSL proposal 0002): publish `allowed_signers` lines with `namespaces="packet/envelope"`;
  principals must not start with `#`.
- Confirm `single-tenant/device_agent/device/<id>` for WatchTower-verified devices (Contribution Ledger).
- Grant namespace `dodwk.packet.v1` to the operator principal that signs DoD Witness Kit certifications
  (`dodwk sign-cert`; proposal 0027). The kit refuses principals, namespaces or key ids with whitespace or control
  characters.
- Issue principals: Courier nodes (`single-tenant/device_agent/courier/<node-id>`, namespace `courier/message`),
  Covenant Gate's decision signer (namespace `covenant-gate/decision`), Echo's producer (namespace
  `packet/envelope`), LawVM seal signers (NeverLost proposal 0002). Publish the bundle hash out of band.
- Owner: `main` cannot be pushed (build files over 100 MB in its history).
- Registry drift from NeverLost proposal 0003, applied in proposal 0024: `constellation`, `lawvm` and `packetpuncture`
  now name `neverlost.trust_bundle.v1`; the reverse `neverlost > watchtower` record is gone (NeverLost has no upstream);
  publish now keeps every `project.contract.json` current, so the downstream list refreshes on the next sync.
- Consumers still naming contracts NeverLost does not publish: PacketPuncture (`neverlost.pledge.v1`), RunLedger and
  BountyGate (`neverlost.allowed_signers.make.v1`, `neverlost.sig.verify.v1`), SoteriaVault (`neverlost.contract.v1`),
  Global Workbench (`neverlost.settings.v1`). NeverLost publishes them, or each consumer re-points to a published one.
- Merge `audit/constellation-readiness-2026-10-15`. Issue production identities for live-state-surgeon devices and a
  real NFL signing key (NFL still uses the dev key in `proofs/keys`).

## nfl
- `receipt-head -Integration <consumer>><provider>` (NFL proposal 0003, read-only): an emitter asks which receipt NFL
  witnessed last, so a rewritten or removed witnessed receipt is caught even when the emitter's local records changed too.
  First user: Recognition (proposal 0033). Run `_RUN_nfl_selftests_v1.ps1` on Windows (new stage `RECEIPT_HEAD`, 9/9).
- Prefer `.constellation/integrations.json` (published) over parsing the service map.
- Add a receipt inbox for DoD Witness Kit's own run ledger (proposal 0027): `{ "name": "dodwk-certification-runs",
  "path": "../dod-witness-kit/proofs/receipts/certification", "mode": "receipt" }` - no `integration` field (it is not
  an integration record); lines are `dodwk.certification_receipt.v1`, chained by `prev_sha256` like integration
  receipts.
- Receipt inboxes in `config/inbox_registry.json` now cover Courier, Echo, DoD Witness Kit, the workbench, Contract
  Registry and Contribution Ledger. The Witness Receipts button drives `witness-receipt` / `verify-receipt` for
  every emitting record.
- NFL proposal 0002, applied in proposal 0017: family `nfl.ledger` added; `runledger > nfl` carries `nfl.receipt.v1`
  (not RunLedger's own `nfl.receipt.ingested.v1`); the frozen `nfl.tier0.selftest.v1` is off `watchtower > nfl`;
  `live-state-surgeon > nfl` is `declared`. Still open: `global-workbench > nfl` names `nfl.settings.v1`, which NFL
  does not define (Global Workbench owner to say what is meant).
- Packets, not receipts, from WatchTower: ingest only checks them with CPR; record their hashes so WatchTower's
  packets are actually witnessed. Ingest must run from the dev root on any OS, not only from one fixed Windows drive path.

## nfl producers (rebound, runledger, anchormark, ...)
- `nfl.ingest.v1.packet_id` is the producer's declared id only: NFL keys on the CPR-verified packet id and records
  yours as `declared_packet_id`. List `payload/nfl.ingest.json` with its SHA-256 in the manifest, or NFL refuses the
  envelope. Use NFL's `schemas/nfl.ingest.v1.schema.json` as the authoritative copy.

## observatory
- `observatory > hashcanon` is **emitting** (proposals 0025, 0026). Every built packet, and every `observatory verify`,
  goes through HashCanon's `hashcanon_verify_packet_optionA_v1.ps1`; a rejected packet is quarantined and never
  published. The record has no contract, so receipts carry `contract: null` and an empty `carried`; request =
  the packet's `manifest.json` bytes (PacketId), response = the verifier's stdout. HashCanon's own
  `hashcanon.verify_receipt.v1` is kept locally and linked from Observatory's run receipt.
- `observatory > covenant-gate` (`covenantgate.eval_output.v1`) is **emitting** (proposal 0019). Every AI assessment
  is an `ingest.packet` / `ai_assessment` / `admit` evaluation through Covenant Gate's `scripts/cg_eval_cli_v1.ps1`
  against Observatory's pinned base policy; Observatory recomputes `input_hash` and `evaluation_id` and checks the
  pinned effective-policy hash. Receipts: `proofs/receipts/integration/observatory__covenant-gate.ndjson`, one per
  evaluation, `unavailable` and `failed` included.
- `observatory > neverlost` (`neverlost.trust_bundle.v1`) is **emitting**: one receipt per trust-bundle load
  (`observatory__neverlost.ndjson`). Packets are signed in namespace `observatory/packet` by
  `single-tenant/device_agent/observatory` (`OBSERVATORY.cmd setup` creates the key on the owner's machine).
- Witness all three with `cn witness` once Observatory has run on Windows (receipts are local, not committed).
- Official website (proposal 0031): `site/` is built and on `main` after the next sync. Owner: create the Vercel
  project `observatory-site` (root `site`), add the domain, add the Cloudflare `CNAME observatory`, then add it to
  `site/src/data/websites.json`.

## pie
- `pie > haai` is **emitting** (proposal 0034): `pie haai capture` and `pie memory haai-sync` go through HAAI's own
  exporter and write one receipt per attempt to `proofs/integration_receipts/pie__haai/receipts.ndjson`. Witness it
  with the Witness Receipts button once real captures exist.
- `pie > veritas-engine` (planned): `veritas-aion check-envelope` per signed packet, receipt per call. Veritas found
  that `proofs/runs/pie0`'s signature does not verify: re-sign it, cover `sig_envelope.v1.json` and `signatures/`
  in `sha256sums.txt`, put real keys in `proofs/trust/`, drop the absolute `packet_root`. Re-signing needs the
  owner's signing key, on the owner's machine.

## pie-model
- Registered (proposal 0034): builds the PIE model from opted-in, verified exports and publishes sealed releases
  (`pie.model.release.v1`). It consumes `pie.training.export.v1` (`pie-model > pie`) and `haai.training_example.v1`
  (`pie-model > haai`); write a receipt per import. PIE installing a release is a contract, not a service
  dependency, so there is no cycle.
- `pie-model > veritas-engine` can now be proposed if releases should be checked by Veritas.

## rebound
- Scope decided: option A (proposal 0025); the registry role now covers the hosted mail product. Session lengths: the
  platform owner's never expire; admins' are set by their supervisors or the platform owner. Record this in the
  canonical docs.
- Classified (proposal 0023): outbound and inbound email, relay addresses and aliases, mailboxes and embedded
  messaging, delivery events and webhooks, its own accounts; families `rebound.email.send`, `rebound.webhook.event`,
  `rebound.relay_address`. Until the owner rules on scope (Decisions), do not grow the product further.
- `rooted > rebound` (`rebound.email.send.v1`, `rebound.webhook.event.v1`) is recorded as the live consumer; Rooted
  writes the receipts. `proteusops > rebound` is planned. `rebound > nfl` is `declared` only (no NFL path in the hosted
  service). NeverLost and Covenant Gate no longer list Rebound downstream: no code uses them.
- Release: wire the e2e suite and `build_release.ps1` into `release.ps1` (or rewrite `RELEASE_v1.md` to what is
  enforced); commit Constellation publishes (`.constellation/`) on their own, not inside the release commit.
- Outside Rebound: gi-ppi.com's SPF record starts with a space; rootedapp.net has no bounce domain and still includes
  mailgun.org.
- `rebound > covenant-courier`: replace the bridge's fast-smoke proof with a real `courier.ps1 deliver` call, write
  Rebound's receipt (Courier's hand-off has the exact fields; `scripts/_lib_constellation_integration_receipt_v1.ps1`
  in Courier writes the byte form), pass `-CourierRoot` explicitly (Courier is in `_Covenant-systems`), and run
  Courier on the current PowerShell host.

## recognition
- `recognition > soteriavault` is **emitting** (proposal 0033; Recognition proposal 0005): every SoteriaVault link check writes
  a receipt to `proofs/integration_receipts/recognition__soteriavault/receipts.ndjson`, witnessed by the browser (encrypted
  action ledger) and handed to NFL at once when NFL is found; before each append the browser asks NFL `receipt-head` and
  refuses if NFL's last witnessed receipt is gone (`RECEIPT_NFL_MISMATCH`). NFL inbox `recognition-soteriavault-receipts`.
  Next: Recognition `UPDATE_ALL` on Windows, then "9 - Witness Receipts" to reach `witnessed`.
- `recognition > neverlost`, `recognition > covenant-gate`: no exchange yet, so no receipts (stay `specified`).

## relaymesh
- `relaymesh > dod-witness-kit` (`dodwk.adapter_export.v1`, `specified`; proposal 0027): write the receipt per
  export; stop `-MirrorToDodwk` (producers never write into the kit's folder); remove absolute paths; give RM-05
  evidence or mark it blocked (the kit recomputes 7000 bp, not the claimed 8000, and refuses the bundle). The kit's
  importer now also requires exactly the five documents plus a sorted, LF, BOM-free `sha256sums.txt`, a producer
  receipt that lists every document, and `progress_percent` equal to the recomputed basis points / 100.

## rooted
- `rooted > rebound` is the live mail link (proposal 0023): write a `constellation.integration.receipt.v1` per send
  and per webhook received, with positive and negative tests, then ask for `emitting`.

## soteriavault
- Its four connectors (`> watchtower`, `> neverlost`, `> rebound`, `> recognition`) write receipts; they move to
  `emitting` after a green Windows `update.cmd -Release` with a counterpart inbox configured: send the run's output.
- Registered (proposal 0017): `soteriavault.attestation.v1` on `> watchtower` and `> neverlost`,
  `soteriavault.connector_grant.v1` on `> rebound`; receipts may name them in `carried`.
- NFL is found by the service id `nfl` in `.constellation/integrations.json` and the dev-root layout, never by path.

## proteusops (Podsteps)
- Registered under its old id; the folder is `_Venture-Systems/podsteps`. OAuth callbacks are now bound to the
  browser that started them (Podsteps `OAUTH_CALLBACK_BROWSER_BINDING_v1`). Its OAuth server boundary is an owner
  decision (Decisions).

## themeforge
- `themeforge > recognition` is **emitting** (proposal 0021): `themeforge publish-recognition <theme>` adds the theme to
  Recognition's `themes/library.v1.json`; receipts in `proofs/integration_receipts/themeforge__recognition/`. NFL inbox
  `themeforge-recognition-receipts`. Next: witness (Witness Receipts button).
- Provides `themeforge.api.v1` (`themeforge api`) for `global-workbench > themeforge` (**emitting**, receipts written by
  the workbench) and the extension UI kit `themeforge.tokens.v1` for `cookiegate > themeforge` and `shadowprofile >
  themeforge` (specified).
- Website: theme.theconstellationnetwork.com (Vercel project `themeforge-site`).
- Store publishing (proposal 0022, external stores, not Constellation integrations): listings `themeforge.listing.v1`,
  submission to Chrome Web Store, Firefox Add-ons and Edge Add-ons after a one-time connection, kits for Opera and
  GX.store; log `proofs/store_submissions/<store>.ndjson`. Owner: connect the stores once (docs/STORES.md).

## triad
- Sign restore attestations by default (owner, 2026-10-21): make signing the default path with the NeverLost key; an
  unsigned attestation is only produced, and labelled, when signing is unavailable.
- `triad > neverlost` and `triad > archive-recall` are **emitting** (proposal 0023); `triad > archive-recall` now
  names `archive_recall.snapshot_manifest.v1`, so change the one table entry in
  `scripts/lib/triad_integration_receipt_lib_v1.ps1` (its drift selftest fails until both sides agree). NFL has receipt
  inboxes for both.
- Restore attestation (`triad.attestation.restore.v1`) is built with schema, vectors and an external verifier; the
  receipt-chain binding for prepare/verify/commit is still open.

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
