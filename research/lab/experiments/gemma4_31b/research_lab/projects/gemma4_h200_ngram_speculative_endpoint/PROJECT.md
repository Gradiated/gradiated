# Native n-gram speculative endpoint

## Question

Can SGLang v0.5.13's native n-gram speculative path reduce target-model decode work on the exact prompt-heavy Gemma 4 workload without the assistant-model and target-verify overhead that made Frozen-KV MTP 89.86% slower?

## Why this matters

The retained exact stack serves the workload at `0.674325859 s/request`, while the sustainable H200 ceiling is `0.6381105231 s/request`. The failed MTP endpoint accepted 4,880 drafts but required 354 serial assistant/verify iterations; target verification alone cost `0.811779555 s/request`. Native n-gram speculation is materially different: the pinned runtime has a distinct `NGRAMWorker` route and can propose from already-observed token sequences without another model forward. It is therefore a cheap, quality-preserving falsifier of whether repeated text in this exact traffic can remove enough target decode steps to close the remaining 5.37% service-time gap.

## Bound scope

`EVIDENCE_BINDING.json` fixes the checkpoint, runtime, image, workload, current control, and source evidence. Preserve the producer-fused metadata, dense penalizer add, dynamic FP8, fused QKV, deferred-local-KV, sampling, cache, and request identities. This project may enable exactly one source-supported native n-gram contract. It may not use an assistant checkpoint, change outputs, change sampling, alter request geometry, or sweep n-gram/proposal settings.

## Experiment

Before claiming a GPU:

1. Bind the live v0.5.13 n-gram worker, scheduler integration, server arguments, proposal length, match depth, acceptance accounting, and target verification path.
2. Select one runtime-native contract from source and defaults. Record it before execution; do not optimize it against this workload.
3. Derive the minimum accepted-token or target-forward reduction required to beat `0.6381105231 s/request`.

After the `$8.00` reservation is durable, claim `h200-sync-linear-e00vhh6h29fj68x91g` only if its watchdog leaves enough time for a bounded run. Run one representative exact-request diagnostic with candidate-path, proposed-token, accepted-token, verify-iteration, and target-forward telemetry. If the measured conservative bound is below 3% and cannot reach the ceiling, close without an endpoint pair. Otherwise run exactly one profiler-off c32 control/candidate pair.

Require 32/32 finite nonempty outputs, exact `117728` fresh plus `17120` cached prompt-token accounting in each scored arm, unchanged generated-token counts, real n-gram path proof, and no assistant-model execution. Retain a simple gain; production promotion requires service time at or below the ceiling.

Do not replay MTP, repair its accounting, sweep speculative settings, change fallback thresholds, tune cache geometry, or create a provider resource.

## Resources and limits

- Bench: retained `h200-sync-linear-e00vhh6h29fj68x91g`.
- Spend: `$8.00`.
- Compute: at most 60 claimed H200 minutes.
- Wall clock: at most two hours from first researcher start.
- Storage: at most 6 GiB retrieved artifacts.
- Reuse the resident checkpoint, pinned image, current-stack bytes, and CUDA/Triton caches.

## Decision

Keep a coherent measured improvement as an incremental stack candidate. Close native n-gram speculation if acceptance/target-forward evidence cannot support 3%, if the exact endpoint is not faster, or if output/accounting/path gates fail. A negative closes only this one frozen native contract.
