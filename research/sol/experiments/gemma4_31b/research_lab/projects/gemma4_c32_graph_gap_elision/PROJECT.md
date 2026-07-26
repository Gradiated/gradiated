# Gemma 4 c32 CUDA-graph gap elision

## Question

Can one source-level scheduler or CUDA-graph state transition change remove a
measured non-overlapping host/launch gap from the exact Gemma 4 31B c32
endpoint and reduce service time without changing checkpoint values, request
ownership, emitted tokens, cache accounting, or serving features?

This is materially independent of hybrid attention placement and the closed
FP8 weight-stream build lineage. It targets only scheduler-visible and
inter-kernel dead time around the current quality-qualified endpoint.

## Why it matters

The locked qualified denominator is `0.625149101968745 s/request`; the campaign
target is `0.500119281574996 s/request`. The exact endpoint saturates H200 in
coarse telemetry, but that does not exclude removable host, graph-transition,
or launch gaps. A small exact gain is useful because it stacks with the
qualified runtime.

## Bound identities and resident resources

- Model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime image:
  `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Workload/source packet identity:
  `4ae9a81bfe3cfcc45a5302662be380e70c2753ef336547445b85aa7ed28f7f4b`.
- Resident source snapshot identity:
  `24ab206cd853d9344bc74adc7cd4c68e7fa9234caa38ea4ca061a4b9445ee976`.
- Authoritative model configuration:
  `../gemma4_h200_ngram_persistent_grouped_lm_head/inputs/bound/config.json`,
  SHA-256
  `e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`.
- Discovery trace:
  `../gemma4_h200_ngram_persistent_grouped_lm_head/inputs/bound/TRACE_ANALYSIS_REPAIR.json`,
  SHA-256
  `a22e25b3e911891d75e1008f22a03ad2a7d160584e1c83e660b8a3238602304f`.
  It reports a measured `157856.86328125 us` `gpu_idle_or_host_gap`
  proxy in a `2375141.908203125 us` H200 window. Treat this as discovery
  evidence only: the trace is asynchronous and n-gram-instrumented, so the
  proxy is neither additive nor transferable to the exact endpoint result.
- Shared bench: `h200-dflash-adapter-e00vyqp7gxsr34wrtz`. Read its current
  connection identity and lifecycle from `../../runtime/gpus.json`; never use
  a copied endpoint. Exact checkpoint, image, runtime source, and CUDA caches
  are warm. No server or experiment process is resident.

## Work contract

Use `$kernel-research`.

1. Reuse the exact qualified c32 request packet and pinned endpoint runner.
   Start from the hash-bound discovery trace above; do not open a new profiling
   lineage before choosing an intervention.
2. Name the exact production producer and consumer symbols spanning one
   scheduler/CUDA-graph boundary and one causal limiter. Bind the exact phase,
   batch/sequence geometry, tensor layouts and dtypes/scales where tensors
   cross the boundary, graph mode, and target H200. Implement exactly one
   source-level intervention. Do not run a flag sweep and do not stop at
   profiling.
3. Before claiming the bench, persist `SOURCE_READY.json` containing the
   intervention/source hashes, exact stock/candidate launcher, predicted
   physical change and predicted movement in the named gap/launch count,
   required output/accounting invariants, and a static proof that both arms use
   the bound model, image, workload packet, concurrency 32, and output length
   358. The pair must preserve the call chain
   `endpoint_pair.py:arm -> run_c32 -> exact_runner.py:main`; only the
   hash-bound candidate source differs.
4. Atomically claim the named H200 only after that terminal exists and the
   current pool record is available with the 05:20Z watchdog. Mutable repairs
   are limited to import, path, permission, build, or process-local attachment
   defects; model, image, workload, arm semantics, and quality gates are
   immutable.
5. Run one profiler-off matched pair: stock c32 first, then the candidate c32.
   Require 32/32 complete requests per arm, finite nonempty outputs, exact
   target/emitted-token equivalence, identical prompt/completion/cache
   accounting, and no request errors. Persist raw per-request timing and token
   identities.
6. A valid positive result is retained even below 5%. A non-positive valid
   pair closes only this source intervention. Any output or ownership
   divergence is localization evidence and forbids a performance claim.

Use the proven resident endpoint packet and pair machinery indexed by the
bench contents; do not rebuild common workload or checkpoint plumbing.

## Budgets and terminal

- Researcher wall clock: 55 minutes.
- GPU claim: at most 30 minutes, claim by `2026-07-26T04:40:00Z`, release by
  `2026-07-26T05:10:00Z`.
- Provider spend: at most `$3.00` cumulative.
- Storage: at most 4 GiB of new non-checkpoint artifacts.
- Provider mutation: forbidden.

Write `C32_GRAPH_GAP_ELISION_TERMINAL.json` with a typed valid positive,
valid non-positive, correctness/ownership divergence, source-level
falsification, or bounded infrastructure result. Stop experiment processes and
release the bench warm before returning.
