# SGLang v0.5.12 Gemma 4 stock/MTP H200 endpoint

## Decision question

Can the exact pinned Gemma 4 31B checkpoint on one H200, served by SGLang v0.5.12 with BF16 weights and FP8-E5M2 KV, clear the campaign's `0.47201182295214134 s/request` c32 economic ceiling; and does the release's native Gemma 4 MTP path reduce matched all-in service time by at least 5% with identical deterministic output IDs?

This is a materially different full-stack intervention. The W4 vLLM line and B200 NVFP4 transfer are closed. Their terminal evidence leaves a large unattributed norms/activation/rotary/sampling/runtime residual. The current official SGLang release adds Gemma 4 support, Gemma 4 MTP, speculative-decoding overlap, fused Gemma 4 RMSNorm/residual work, and reduced logits-copy overhead. Those changes act on the unresolved full-stack path rather than repeating a linear or attention component.

## Immutable inputs

Consume and mechanically verify `BINDINGS.json` before provider creation. In particular:

- target `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4` from the existing verified eight-file, `62,578,655,208`-byte checkpoint;
- assistant `google/gemma-4-31B-it-assistant@627c5ec1458b9086b841a91e0512fd31fd2fbbf1`;
- SGLang v0.5.12 source commit `127b9e3283f7c2a43234b852ff5c9f1796d53624` and linux/amd64 image `docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`;
- exact content-bound 4,214-input/358-output trace with 12.7% cache reads;
- one H200 SXM, TP1, BF16 target weights, and FP8-E5M2 KV.

Materialize and content-hash the small assistant locally in this project if it is not already complete. One bounded local owner is allowed if needed; provider create remains gated on its typed pass. Do not redownload or rewrite the verified target checkpoint. Resolve the official release's native MTP arguments from the pinned source/recipe, record them, and use that release path rather than carrying forward the older project wrapper.

## Retained execution

Use the proven Nebius create/SSH/watchdog/authenticated-cleanup lifecycle and the shared retryable-operation/repair-lease protocol. Reuse the corrected owner geometry identified by `../h200_w4_full_endpoint_background_frontier/h200_endpoint_owner.py` (`sha256:58332df4461c3e17e351eacbb0644dcdd4a375f6b95d2a3e2813152cec7ebd1a`) without inheriting its vLLM program or W4 constants.

Create one mutable retained H200 development owner. Transfer the bound target and assistant with authenticated host-key options, content manifests, size-derived timeouts, phase-split diagnostics, and remote hash verification. Keep the same resource through image pull, model load, stock measurement, server restart, and MTP. Use `run_repairable_operation` for remote stages so ordinary import, argument, path, runtime, telemetry, or first-call defects can be patched and retried in place. Never suspend the controller; the absolute watchdog and authenticated cleanup remain authoritative.

Run sequentially:

1. Stock SGLang at c32 on the exact campaign trace. Require at least 32 complete, nonempty, failure-free requests, exact token accounting, and separate queue/TTFT/prefill/decode/service metrics. Capture server/runtime identity, request rows, SGLang scheduler/spec metrics, continuous GPU telemetry, memory/power, and actual provider exposure.
2. If stock is structurally valid and at least 20 provider minutes remain, restart only the resident server into native Gemma 4 MTP, initially using the bound one-token proposal contract unless the pinned release requires a source-equivalent spelling. Repeat identical request bytes and deterministic diagnostic prompts. Capture accepted draft tokens, draft/verify calls, output IDs, complete requests, and phase wall times.

Do not run c1/c4/c8/c16: existing scope-matched H200 BF16 component floors close them or make them lower-value. Do not add a vLLM cold control, prefix-cache arm, 10K view, checkpoint representation, or B200 placement. Broad production quality remains deferred.

## Acceptance and terminal

- Market pass: c32 stock or MTP complete-request service time `<=0.47201182295214134 s/request` (`>=2.118591 requests/s`) using actual completed requests and provider exposure.
- MTP promotion: identical deterministic output IDs, no nested/empty results, at least 32 complete requests per matched arm, and `>=5%` all-in service-time/cost reduction versus resident stock. Record mean accepted tokens and compare it with the content-bound MTP threshold; `>=10%` is a strong promotion.
- A valid stock miss plus valid MTP miss closes this SGLang/H200 route. An invalid MTP arm does not erase a valid stock result.
- A pre-science transport or integration failure is operational evidence; repair it in the same retained owner while time remains. At the absolute limit, emit a typed failure and authenticated zero-resource cleanup without scientific inference.

Return one atomic terminal containing stock and, when admitted, MTP rows; exact identities; acceptance/output checks; economic classification; provider exposure/spend; and verified zero matching instances/disks.

## Budgets

- Researcher profile: `execution`.
- Wall clock: 140 minutes.
- Provider exposure: 85 minutes / 1.4167 H200-hours cumulative.
- Compute: one H200; local preparation at most 1.5 CPU-hours.
- Storage: one 250-GiB provider disk, 4 GiB project-local preparation, and at most 10 GiB retrieved artifacts.
- Spend: `$3.75` including disk and cleanup margin.

The owner is exclusive only for its instance/disk mutation and cleanup. No duplicate allocation is admitted.

## Director follow-up — 2026-07-20 current-runtime FP8 MTP unlock

The v0.5.12 branch is terminal only for its bundled Transformers parser: it could not load the exact `gemma4_assistant` config, so it produced no MTP result. The campaign now has a proven target path at `0.748553484718741` seconds/request using in-memory FP8 linears, and MTP is independent of the QKV epilogue stack. Reopen the same scientific question against current upstream support; do not reuse the invalid `0.363303` fully cache-read stock artifact as a comparator.

Work offline while the QKV stack owns the retained H200. Inspect the exact assistant config/revision already materialized, the exact target geometry, current Transformers config registration, and current SGLang target/draft integration. Produce one content-addressed runtime commit/image or minimal source patch that can actually load both exact revisions and preserve the proven target's in-memory FP8 linear consumer. This requires mechanism-level reasoning across the assistant architecture, speculative scheduler, quantized target path, and Hopper execution, so this follow-up is `deep`. If no real FP8-compatible target/draft consumer exists within the local support budget, emit `runtime_unavailable` without claiming a GPU; do not build a compatibility facade or benchmark a synthetic assistant.

Only after a local typed support terminal and after the QKV project releases may this project claim `h200-kernel-frontier-e00pfvrckjvwn7bhet`. Reuse the exact checkpoint and assistant bytes, and run one same-session FP8 stock c32 control plus one MTP c32 candidate with identical request bytes. Require 32/32 valid rows, exact token/cache accounting, accepted-draft and verify-call telemetry, current smoke semantics, proven FP8 target consumption, and deterministic diagnostic outputs. Promote at `<=0.7145910375209391` seconds/request or at least a stable 4.537% reduction from the same-session FP8 control; retain a smaller simple positive result, and stop after one proposal contract. No provider creation, BF16 fallback comparison, proposal-depth sweep, or broad quality run is authorized.

## Director follow-up — 2026-07-20 repaired FP8+QKV MTP residual

The current-runtime support gate and model load passed, but the prior MTP candidate consumed its first diagnostic at the eager buffer registry shape boundary (`[1]` versus `[18]`) before draft acceptance or verify telemetry. That unchanged candidate is closed. Source inspection already identified `SGLANG_EAGER_INPUT_NO_COPY` as the bounded semantic repair, and it has not been executed. The residual campaign explicitly keeps this route admissible after the exact FP8+QKV profile closed only its stream-interval intervention.

Use the already registered H200 `h200-v0513-fp8qkv-e00t4pa49nhc2g7jwe` after the increased reservation is durable. Bind the exact current v0.5.13 FP8+QKV bytes and repair bytes locally, prove the corrected prompt-shape path on one fresh non-benchmark diagnostic, and run one contemporaneous c32 control/candidate pair. The candidate is FP8+QKV+MTP; the control is the identical FP8+QKV endpoint without MTP. Require 32/32 exact-mix rows, exact cache accounting, FP8/QKV consumers, accepted-draft and verify telemetry, and deterministic smoke semantics. The campaign ceiling is `0.6381105231 s/request`; a stable gain below 5% is evidence but closes this route. Do not replay the unchanged failure, sweep proposal geometry, fall back to BF16, or regenerate quality captures. Release by `2026-07-20T11:10:00Z` under the existing watchdog.

## Director follow-up — 2026-07-23 accepted-depth discriminator on the stacked frontier

The repaired July 20 candidate completed requests but emitted no accepted-draft or verify telemetry and left the target FP8/QKV audits empty. Its `0.6878272985 s/request` label is therefore not MTP evidence. The campaign now has a different stacked frontier at `0.6746877474 s/request`, including deferred local FP8-KV commit, pinned penalty-token transfer, host-required dense add, and producer-fused SWA translation.

Keep the same MTP scientific project. First bind the exact v0.5.13 target/draft worker and scheduler sources that produce assistant forwards, target verifies, drafted tokens, accepted tokens, and accepted depth. Freeze one real-path discriminator and at most one source repair needed to expose that native path; do not build a synthetic assistant or telemetry facade. After the higher-priority residual-H2D project releases the shared H200, run one representative GPU diagnostic with the exact target, assistant, and stacked consumers.

Only if measured accepted depth and target-forward reduction imply at least a 3% whole-request gain after assistant/verify overhead may the researcher run one contemporaneous stacked c32 control/MTP pair. Require 32/32 exact accounting, real assistant/verify/acceptance telemetry, retained target path proofs, and deterministic smoke outputs. Close without an endpoint if speculation is inactive or the bound misses. One proposal contract only; no depth sweep, BF16 fallback, prior-arm replay, or new provider resource. The binding is `ACCEPTED_DEPTH_REOPENING.json`.
## 2026-07-23 — target-only QKV with stock KV-shared assistant

The prior current-stack attempt proved that native `FrozenKVMTPWorker` entered the real Gemma4 assistant, but the installed target QKV epilogue partially executed in a KV-shared assistant layer and correctly raised its exclusion guard. That consumed the guarded candidate, not the broader accepted-depth question.

This iteration admits one different consumer contract: keep the exact measured fused-QKV path on target layers and dispatch only KV-shared assistant layers through their stock supported QKV implementation. First prove both sides of that dispatch and collect nonempty accepted-draft/verify telemetry. Run one c32 control/MTP pair only if the measured diagnostic predicts at least 3% whole-request improvement. The model, target and assistant weights, runtime/image, workload, cache, sampling, and speculation geometry are immutable; no parameter sweep, BF16 arm, or replay of the guard-raising candidate is allowed. The full contract is `KV_SHARED_ASSISTANT_REOPENING.json`.
