# Research log

## 2026-07-16 — Director queued execution handoff

- The proven r4 H100 vLLM route loaded exact BF16 at `77,025/81,559 MiB` and completed three 36-case development captures; its only outer failure was a legacy AWQ allocation-result retrieval expectation.
- Preregister one direct holdout-control session at `$3.23`/3,000 allocation seconds, but do not activate it until the scoring seal is repaired and the live AA owner cleans to authenticated zero inventory.
- No retained follow-up is allowed despite setup dominance: a later AWQ arm uses a different checkpoint and L40S runtime, so it cannot reuse only content-bound BF16 state. Clean normally.

## 2026-07-16 — Director keeps paid trigger closed

The scoring-seal audit reproduced a JSON-schema failure and found that the V3 scorer does not consume the manifest-bound seven-file capture evidence. Replace the first queue trigger with `HOLDOUT_EXECUTABLE_BRIDGE_PASS`; authenticated AA cleanup remains the second. Do not create H100 capacity from `HOLDOUT_CONTRACT_RESEALED` alone.

## 2026-07-16 — Director activates direct execution with a hard consumer gate

AA is terminal and authenticated inventory is zero. Independent audit rejects the final bridge as `QUALITY_POLICY_CLOSE`: JSON scorer ingestion, future seven-file-to-score derivation, execution identity, and fail-closed mutations remain defective. Do not open another repair project. Correct those exact consumer boundaries as one hard pre-create gate inside this execution project; if all focused positive/negative tests pass, launch the one H100 owner in the same researcher turn. Otherwise close quality with zero creates and no readiness successor. The `$3.23`/3,000-second, one-create/no-retry/no-retention contract is unchanged; H100 retention remains scientifically invalid because the later AWQ candidate needs a different checkpoint, L40S hardware, and runtime state.

## 2026-07-16 — Hard pre-create consumer gate closed quality with zero spend

- Action: ran the resealed validator, historical r4 bridge test, 43 shared-launcher tests, and an independent normal JSON serialization through the named on-disk scorer.
- Evidence: the historical controls pass, but `score_resealed_holdout.py` raises `ValueError: capture_ordinals` once ordinal object keys round-trip as JSON strings. The live vLLM path also still stages `executable_development_v2/development.jsonl` with its fixed development SHA, rather than the resealed holdout.
- Interpretation: this is exactly the future-consumer/identity boundary the Cycle 124 gate requires. Existing historical captures do not repair it; a H100 session would be incapable of producing a valid post-development holdout artifact.
- Decision: `QUALITY_POLICY_CLOSE`, zero inventory queries and zero creates. Durable evidence: `artifacts/QUALITY_POLICY_CLOSE_2026-07-16.json`.
