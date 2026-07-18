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
