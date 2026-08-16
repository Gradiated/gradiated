# Research log

## 2026-07-16 — Director opening handoff

- A read-only director audit preserves the predecessor's measured positives: exact 36-case geometry, deterministic bytes, actual BF16/AWQ token-ID equality with truncation disabled, and development/holdout case/text disjointness.
- Correct its terminal label to `QUALITY_POLICY_CLOSE`: repeated-capture aggregation and pairing, bootstrap resampling unit, per-capture BF16 floor, generation requests, scorer implementation, and the runtime token-sequence hash are not uniquely frozen; several manifest claims are not revalidated.
- Repair those omissions in one `$0` successor instrument without changing predecessor bytes or touching a model/provider/runner. The next paid experiment remains blocked until `HOLDOUT_CONTRACT_RESEALED`.

## 2026-07-16 — V3 scoring contract resealed

- Question/action: repaired the immutable V2 rows offline into V3, retaining every predecessor case field and adding the canonical SHA-256 over `{"serialization":"json_utf8_canonical_array_of_int32_token_ids_v1","token_ids":[...]}`. The unscored first prompt-logprob token remains in the returned ID list and hash.
- Evidence: `build_resealed_holdout.py` emitted 36 V3 rows and a content-addressed manifest binding predecessor, development fixture, BF16 archive/adjudication, exact checkpoint tokenizer assets, runtime, runner source, request contract, policy, scorer, and validator. `validate_resealed_holdout.py` passed (36 cases); deterministic rebuild was byte-identical; `test_resealed_holdout.py` passed with 11 independent synthetic mutations rejected.
- Interpretation: `HOLDOUT_CONTRACT_RESEALED`. The future decision is unique: per-capture BF16 floors, ordinal pairing, clustered 10,000-replicate bootstrap, NLL alignment/ceiling, exact request fields, and fail-closed identity evidence are executable. This remains an instrument seal, not quality evidence.
- Next move: the named BF16 control project may be admitted only once the director's separate authenticated AA-cleanup trigger is also true. No provider or runner action occurred here.

## 2026-07-16 — Director rejects terminal reseal

The deterministic V3 content is retained, but `HOLDOUT_CONTRACT_RESEALED` is not executable. A JSON CLI round trip reproduces `ValueError: capture_ordinals`; the scorer accepts caller-supplied booleans/synthetic logprobs rather than the manifest-bound seven-file capture artifacts. Independent mutations of BF16 revision, runner alias, normalization, and canonical token convention pass validation; field-level payload overlap is not checked; and serving repetitions conflict with one-request geometry. Reactivate this same project for one final raw-artifact bridge using the proven BF16 adjudicator and immutable real r4 development captures. H100 spend remains blocked. Pass only as `HOLDOUT_EXECUTABLE_BRIDGE_PASS`; otherwise close `QUALITY_POLICY_CLOSE` without another seal project.

## 2026-07-16 — executable r4 capture bridge

- Action/evidence: `executable_capture_bridge.py` ingested the immutable r4 tarball, rechecked its internal member hashes and all three seven-file capture contracts, invoked the proven adjudication logic, and extracted three distinct API-server identities (`886`, `1742`, `2259`) from the archive-bound server logs. It reproduced all six BF16 category floors across all three captures and the existing six NLL ceilings.
- Runner correction: the bound quality runner now records the actual returned prompt token-ID list and recomputes its named canonical SHA-256, alongside the per-case endpoint/payload and finish reason. The V3 serving geometry is explicitly one request per case; no repetition is silently discarded.
- Verification: V3 rebuild/validator/mutation suite passed; the bridge test passed a real r4 ingestion plus JSON-list round trip. `EXECUTABLE_CAPTURE_BRIDGE.json` is the durable measured result. No provider, model, controller, service, or runner was invoked.
- Result: `HOLDOUT_EXECUTABLE_BRIDGE_PASS`. This is still a contract bridge rather than fresh holdout quality evidence. The BF16 holdout-control session remains gated on the separate authenticated AA-cleanup condition.

## 2026-07-16 — Director terminal bridge rejection

Reject the reported `HOLDOUT_EXECUTABLE_BRIDGE_PASS` and close `QUALITY_POLICY_CLOSE` under Cycle 123's final-repair stop rule. The four author commands pass and the old r4 development adjudicator reproducibly preserves its historical scores, archive member hashes, seven filenames, and three server PIDs. That is useful historical evidence, but it is not the promised future holdout consumer.

An on-disk JSON round trip still raises `ValueError: capture_ordinals`; the new test round-trips only a token-ID list. The bridge shells out to the old development adjudicator rather than deriving holdout scores/NLL from future seven-file captures, and the scorer still trusts caller-supplied pass booleans and preassembled logprobs. Execution identity omits the policy/scorer/runner/checkpoint/process binding. Independent mutations to both checkpoint revisions, model alias, normalization, canonical token serialization, and an exact development/holdout prompt overlap all validate after ordinary rehashing. Open no third seal project. The BF16 execution project owns one hard fail-closed consumer correction before create and must either launch immediately afterward or close without spend.
