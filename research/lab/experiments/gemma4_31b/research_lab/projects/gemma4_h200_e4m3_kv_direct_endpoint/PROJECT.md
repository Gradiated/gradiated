# SGLang E4M3 KV direct endpoint on H200

## Question

Does changing only the exact retained SGLang v0.5.13 stack's KV-cache representation from FP8-E5M2 to FP8-E4M3 preserve a credible serving path and improve or at least preserve the exact c32 endpoint closely enough to unlock a Hopper FlashAttention-3 local-attention consumer?

## Why this matters

The production-qualified working stack remains above the H200 ceiling: its durable c32 control is `21.578427489002934` batch seconds, or `0.6743258590313417 s/request`, versus `0.6381105231`. The exact pinned server source rejects FA3 only for E5M2 and states that FA3 supports FP8-E4M3. Current vLLM E4M3 evidence is not transferable: it used BF16 weights, a different runtime, and measured `0.939163366 s/request`. This project measures the representation change on the retained dynamic-FP8/QKV/deferred-local-KV/simple-gain SGLang stack.

This is the direct endpoint lane. It does not claim that E4M3 alone is a kernel optimization; it establishes the exact endpoint and numerical comparator needed by the independent local-FA3 mechanism project.

## Immutable identity

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Checkpoint index SHA-256: `d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2`.
- Runtime: SGLang v0.5.13 commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2`, Linux/amd64 image `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Retained representation: dynamic in-memory FP8-E4M3FN linears, authoritative QKV epilogue, deferred local-KV commit, producer-fused metadata, dense-add simple gain, TP1, dynamic chunking at 2,048, no MTP or NGRAM.
- Workload: 32 requests at concurrency 32, each 4,214 prompt and 358 completion tokens; exact totals are 17,120 cached and 117,728 fresh prompt tokens.
- Durable comparator: `../sglang_v0512_h200_gemma4_mtp_endpoint/artifacts/mtp-candidate-repair-20260723t0658z/retrieved/control/TERMINAL.json`, SHA-256 `a6e69ac9534ae433fc45d3b5d3ea241fe63321d33423cdd52d17128d8072d278`.
- Source/profile binding: `../gemma4_h200_v0513_fp8_qkv_residual_profile/BINDINGS.json`, SHA-256 `cebc435c4eb1e5716c4aa9bd854785a3e7cac4b0665c96ea6a44040b3e96fb62`.

`DIRECTOR_BINDING.json` and `verify_director_binding.py` mechanically assert these identities before any claim.

## Immediate experiment

After the `$8` reservation is durable, atomically claim available bench `h200-sync-linear-e00vhh6h29fj68x91g`. Reuse its read-only manifest-verified checkpoint, pinned image, current mutable stack, and compiled caches. Stop only an incompatible retained endpoint container after the claim; do not copy the checkpoint or recreate the provider resource.

Launch exactly one candidate with the immutable retained stack and change only KV cache dtype from `fp8_e5m2` to `fp8_e4m3`. Keep Triton as the effective attention backend for every layer. Prove from server arguments, logs, runtime audit, and minimum consumer telemetry that E4M3 is produced and consumed and no FA3, backend fallback, MTP, NGRAM, altered window, or unrelated flag is active. Run one cheap nonzero exact-shape E4M3-versus-E5M2 numerical/coherence discriminator, then one profiler-off exact c32 candidate. Do not replay the persisted E5M2 control.

Require 32/32 complete, finite, nonempty responses; exact request hashes and 4,214/358 usage; exact 17,120/117,728 cached/fresh accounting; no reloads or request failures; and the intended E4M3 path. Persist raw rows, response bytes, server identity, memory/power/utilization telemetry, useful GPU time, actual spend, and a typed terminal.

## Decision

- `retain_direct`: valid candidate below `0.6743258590313417 s/request` with no observed material reliability or coherence regression.
- `hybrid_comparator`: valid candidate that is not faster but leaves a conservative local-attention-plus-FA3 path to beat the current frontier or `0.6381105231` ceiling. Preserve the healthy E4M3 server and exact terminal for the deep project.
- `close`: unsupported or unproven E4M3 consumption, obvious numerical/coherence failure, invalid accounting, or a regression too large for even perfect removal of the measured 15.312032% local-attention boundary to recover.

No precision spelling sweep, FA3 launch, control replay, broad quality run, workload change, or second candidate is allowed here. A performance survivor still requires the campaign's later quality/feature validation before production eligibility.

## Resources

- Researcher profile: `execution`.
- One retained H200; at most 70 claimed GPU-minutes and 100 wall minutes from first claim.
- Provider exposure charged to the lab bench; project authorization `$8.00`.
- At most 6 GiB new local/remote artifacts. No checkpoint duplication.
- Researchers may claim/release the registered bench but may not create, drain, resize, or destroy provider resources.

