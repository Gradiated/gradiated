# SGLang v0.5.12 H200 stock quality and text-feature validation

## Decision question

Does the economically passing exact Gemma 4 31B SGLang/H200 candidate preserve text-only, default non-reasoning behavior when FP8-E5M2 KV is compared with a same-runtime BF16-KV control and a direct Transformers reference sentinel?

The candidate is the campaign's first complete-request market pass: 32/32 exact-workload requests at `0.3633031778 s/request` versus the strict `0.4720118230` ceiling. That result establishes cost and service behavior, not semantic parity. The native MTP arm is explicitly out of scope because the bound image cannot parse `gemma4_assistant` and produced no performance or quality evidence.

## Bound identities and reference

Mechanically verify `BINDINGS.json` before provider creation. Use the exact existing eight-file, 62.58-GB checkpoint and immutable SGLang v0.5.12 linux/amd64 image. The candidate is BF16 weights with FP8-E5M2 KV. The paired control uses the same checkpoint, image, server arguments, prompt bytes, tokenizer/chat template, generation parameters, and H200, changing only KV dtype to BF16. A small direct Transformers BF16 greedy/logit sentinel in the same image supplies an implementation-independent reference for the target checkpoint.

Reuse only the generic raw-capture/evidence/scoring mechanics from the GLM quality interface named in `BINDINGS.json`; do not inherit its prompts, policy, thresholds, manifests, model assumptions, or results. Build a fresh Gemma-specific suite and content-hashed policy inside this project.

## Immediate experiment

Create one mutable retained H200 development owner through the same successful Nebius lifecycle. Transfer and remotely verify the bound checkpoint, pull the same image, and keep the H200 resident across sequential capture arms. Every patchable transfer, launch/readiness, capture, direct-reference, and retrieval stage must actually be called through `run_repairable_operation`; provider create and final authenticated cleanup remain outside it.

Before create, locally build and validate a compact suite with raw request bytes, scorer fixtures, and a typed suite terminal. This is ordinary work inside this paid scientific project, not a separate audit project. The suite must include at least:

- exact JSON/tool-call formatting with executable argument checks;
- sandboxed Python behavior;
- deterministic extraction/math;
- long-context key retrieval near the campaign's 4,214-token geometry;
- multi-turn continuation and chat-template correctness;
- Unicode, stop-sequence, non-streaming, streaming-assembly, and usage/token-accounting behavior;
- deterministic repeat checks;
- at least 128 teacher-forced scored tokens for raw input-logprob/NLL comparison.

Capture raw responses and evidence sequentially:

1. Same-runtime BF16-KV control, twice for deterministic cases.
2. FP8-E5M2-KV candidate with byte-identical requests and repetitions.
3. Direct Transformers BF16 greedy/logit sentinel on the smallest subset sufficient to validate prompt IDs, target checkpoint behavior, and control top-token/logit parity. Do not turn this into a second broad evaluation.

Keep temperature zero/default non-reasoning and preserve exact tokenizer/chat-template bytes. Store raw responses, token IDs/logprobs, request/response hashes, server identity, and capture failures. Score only from raw captures; ignore any model-emitted compliance flag or caller-supplied aggregate score.

## Acceptance and portfolio effect

Pass for text-only, default non-reasoning eligibility only when all hold:

- every critical BF16-KV control case passes its executable scorer;
- FP8-KV has no critical regression and its aggregate executable score is no worse than control;
- deterministic repetitions match within each arm;
- streaming assembled content equals non-streaming content and usage/token accounting is valid;
- candidate teacher-forced mean NLL is no more than `0.03` nats/token worse than BF16-KV over at least 128 raw scored tokens, with no non-finite values;
- the direct reference sentinel validates prompt-token identity and does not expose a control runtime mismatch.

On pass, promote the measured candidate as production-eligible only for text-only, default non-reasoning traffic and retain its measured economic result. Vision/video, reasoning mode, broad safety policy, long-horizon reliability, and MTP remain separate unvalidated modes.

On a valid candidate regression, close FP8-KV quality for this runtime and report whether BF16-KV still has enough measured/derived economic margin to justify a fresh performance arm; do not assume it does. On an invalid control or direct-reference mismatch, quarantine the quality claim and return a typed runtime/reference failure, not a candidate failure.

## Budgets

- Researcher profile: `execution`.
- Wall clock: 120 minutes.
- Provider exposure: 70 minutes / 1.1667 H200-hours.
- Spend: `$3.25` including disk and cleanup margin.
- Storage: one 250-GiB provider disk, 4 GiB project-local suite/captures, and at most 10 GiB retrieved artifacts.
- Local compute: at most 1.5 CPU-hours; one H200 only.

Return one atomic paired-quality terminal with immutable identities, raw-capture hashes, per-case scores, NLL/reference evidence, feature boundary, provider accounting, and authenticated zero-resource cleanup. Repair ordinary first-call defects in place; no duplicate allocation or MTP repair is admitted.
