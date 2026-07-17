# Research log

Delegated in Cycle 56 to adjudicate the already-complete r4 BF16 captures locally. Preserve the immutable archive and frozen prospective gate; separate the legacy outer packaging failure from the scientific score. No model, provider, holdout, or prompt/scorer change is authorized.

## 2026-07-16 — completed offline adjudication

Question: do the immutable three r4 BF16 captures establish the frozen development control and its six NLL ceilings?

Action: implemented and ran `adjudicate_bf16_v2_capture.py` against the archive only. It verified the archive SHA-256, frozen suite/manifest/preregistration hashes, every internal-manifest entry, all capture identities and required artifacts, canonical normalized responses, aggregate and per-row raw-response bindings, finite teacher-forced runtime logprobs, and strict scorer negative controls. Scored all 36 cases independently in each capture.

Evidence: all checks passed. Scores repeat exactly: coding/retrieval/continuation/teacher-forced-loss/serving are `6/6` in captures 1–3; tool-call is `5/6` in captures 1–3, solely `cal_dev_tool_03`. The preregistered minimum is `5/6` per category. `BF16_V2_NLL_CEILINGS.json` freezes the six `1.05 * max(control mean NLL)` ceilings. `allocation-result.json` remains absent only from the legacy outer-controller retrieval convention; it was never a V2 capture-contract artifact and does not affect this scientific result.

Interpretation: establish the BF16 development control and unlock only a bounded recovered-student canary using this identical evaluator. This is neither candidate/holdout quality nor graduation evidence.
