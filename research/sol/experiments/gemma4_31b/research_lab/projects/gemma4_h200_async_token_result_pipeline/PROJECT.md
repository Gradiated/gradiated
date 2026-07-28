# Asynchronous token-result pipeline on H200

## Question

Can the exact one-token serving loop overlap result-token transfer and host request/SSE processing with the next model forward by replacing the synchronous `Tensor.tolist` boundary with one fixed two-slot pinned handoff, without using multi-step decode or a conditional graph?

## Why this matters

The device-conditional discriminator proved that CUDA conditional nodes work on this H200, but the pinned graph captures only `model.forward`. Every step still crosses the host in `BatchResultProcessor._normalize_decode_outputs` through `Tensor.tolist`, then performs request/result processing and prepares the next decode. The exact current trace assigns `34.6096%` to synchronization, `5.7179%` to scheduler gaps, and `1.2106%` to launches.

This project does not retry the closed graph or host continuous-step interventions. It preserves one-token scheduling and every graph launch. The causal change is a two-slot pinned token ring: keep sampled token IDs on device for the next decode input, issue an asynchronous D2H copy on a side stream, and let one bounded host consumer wait on the prior slot to update request state and emit the same ordered SSE token while the next forward is executing. The predicted movement is less result-boundary synchronization wall time with unchanged host call count, token cadence, model kernels, and graph replay count.

## Immutable identity

- Model/runtime/image/checkpoint and c32 workload are the same qualified identities as the control at `0.6743258590313417 s/request`.
- Exact requests use temperature zero, seed `20260718`, 358 forced output tokens, `ignore_eos=true`, and streaming token responses.
- Current source chain: `ModelRunner.sample` returns device token IDs; `BatchResultProcessor._normalize_decode_outputs` calls `Tensor.tolist`; `ScheduleBatch.prepare_for_decode` reconstructs the next input and penalty state.
- The fixed-repeat conditional graph, `--continuous-decode-steps`, schedule-stream snapshot, workload geometry, and streaming semantics are excluded.

`DIRECTOR_BINDING.json` and `verify_director_binding.py` bind the current trace, exact runner, source chain, and completed device-graph falsifier.

## Immediate experiment

Use `$kernel-research` for the CUDA stream/event and runtime integration. Prepare offline behind `gemma4_h200_local_kv_int4_endpoint`. Freeze the live source actually present on the bench, then after a durable `$14` reservation and predecessor release, claim the H200. In the same retained claim, instrument one short exact c32 path to measure the inclusive `Tensor.tolist`/result boundary, then implement the single two-slot pipeline; profiling alone is not a terminal.

The candidate must feed the unchanged next one-token decode from the device token tensor, asynchronously copy those IDs into a preallocated pinned slot, record an event, and preserve exactly ordered per-token host/SSE updates through a bounded consumer. Use the actual sampler, result processor, `prepare_for_decode`, cache accounting, and endpoint transport. The first GPU execution is the discovery test; repair ordinary stream, lifetime, process-local injection, or API defects in place.

Before full timing, run one exact 32-request/16-token discriminator. Require bit-exact token IDs, response order, usage/cache accounting, streaming event count and order, no slot overwrite, correct padded-graph batches, and proof that no host wait on the current token precedes the next forward. Measure inclusive result-boundary distributions and the smallest synchronization/overlap evidence needed. Promote to one profiler-off exact c32 control/candidate pair only if the conservative whole-request bound is at least `3%`. Require 32/32 sane rows and exact accounting.

## Stop rules and resources

Close if the next forward still requires current-token host materialization, streaming order or token/accounting semantics change, the fixed two-slot lifetime is unsafe, overlap is absent, the conservative bound is below `3%`, or the endpoint regresses. Do not batch or delay token emission, change continuous-decode steps, add a conditional graph, alter sampling/workload settings, sweep ring depth, or credit unrelated synchronization.

- Researcher profile: `deep`.
- One retained H200; at most 65 claimed GPU-minutes and 150 wall minutes from first claim.
- Project authorization: `$14.00`.
- Absolute deadline: `2026-07-23T16:20:00Z`.
- At most 6 GiB new artifacts/build outputs; no checkpoint duplication.
- Researchers may claim/release the registered bench but may not create, drain, resize, or destroy provider resources.
