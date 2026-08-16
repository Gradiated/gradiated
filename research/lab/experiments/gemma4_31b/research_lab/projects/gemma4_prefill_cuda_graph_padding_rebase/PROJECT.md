# Gemma 4 prefill CUDA-graph padding rebase

## Question

Does rebasing the exact Gemma 4 c32 path onto official SGLang prefill CUDA
graphs make the upstream excess-padding guard reachable and remove enough
noncompulsory full-model token rows to justify one later H200 component or
endpoint measurement?

## Why it matters

The locked denominator is `0.625149101968745 s/request` and the target is
`0.500119281574996 s/request`. The exact workload is prompt-heavy:
4,214 prompt tokens and 358 output tokens per request at c32. The bounded
upstream screen selected official `PrefillCudaGraphRunner.can_run_graph`, which
rejects graph replay when the selected capture bucket exceeds twice the raw
prefill tokens. That consumer is absent from pinned v0.5.13, so its locked
effect is exactly zero. This project explicitly changes the scientific scope
to the official current prefill-graph runtime and tests whether the exact
workload activates the mechanism.

## Bound evidence and identities

- `../gemma4_upstream_postscheduler_mechanism/UPSTREAM_POSTSCHEDULER_MECHANISM_OFFLINE_TERMINAL.json`
- Official SGLang PR: `https://github.com/sgl-project/sglang/pull/31487`
- Official merge commit:
  `6c6175fabd8eac2ac7a66eea36e6b21fc0893a75`
- Selected source:
  `python/sglang/srt/model_executor/runner/prefill_cuda_graph_runner.py`,
  SHA-256 `498711e4b2607c4256d051ce4c9ed2ba5bdf04f6ee91d55c46734ee572876f1e`
- Exact offline method reproducer:
  `../gemma4_upstream_postscheduler_mechanism/run_offline_consumer.py`,
  SHA-256 `fae79aa6fd61728472f3d6a4e32827167cc8bfe094ac994cb6c399b965b0592b`
- Preserve the exact checkpoint revision, dynamic-FP8 representation,
  hybrid-attention geometry, c32 workload, dynamic chunking, and locked
  request/cost denominator.

Do not transfer the upstream vendor benchmark. It is only source evidence.

## Scope

Work for at most 90 wall-clock minutes and `$0`. Rebase only the minimum
official source needed to route the exact Gemma c32 prefill producer through
`PrefillCudaGraphRunner` and its `can_run_graph` decision. This is not a
generic SGLang comparison, flag sweep, or another source survey.

Trace the real ownership chain from scheduler `ForwardBatch`, raw input-token
count, dynamic-chunk segmentation and capture-bucket selection through graph
eligibility, graph replay or eager fallback, model forward, logits, and KV
ownership. Implement the current-runtime integration through that first
decision-bearing consumer. Preserve model, token, position, quantization,
attention, cache, and output semantics; the candidate may change only the
execution route and padded work.

Reconstruct the exact c32 prefill sequence from content-addressed workload and
launch artifacts. Report every raw chunk, chosen capture bucket, padding
ratio, guard decision, and compulsory versus padded model-token rows. Compare
the same rebased source with the guard enabled and disabled. Credit no timing
from padded-row counts alone: produce a complete analytical interval and one
real later H200 command that measures both routes contemporaneously, or typed
`none`.

Return typed `none` if the exact Gemma/dynamic-FP8 producer cannot reach the
official runner, the exact workload never crosses the guard, required current
source changes model semantics, or no source-complete H200 consumer can be
formed.

Do not claim a GPU, use SSH or provider APIs, run CUDA or an endpoint, copy or
read checkpoint shards, stage model files, change batch/concurrency/chunk
parameters, sweep capture buckets, or reopen the rejected group-quant or
HPC-Ops candidates.

## Terminal

Persist `PREFILL_GRAPH_PADDING_REBASE_OFFLINE_TERMINAL.json` containing:

- official and local source revisions, URLs, retrieval time, and direct hashes;
- exact workload, launch, runtime, and implementation identities;
- source-complete producer/consumer ownership and semantic contract;
- raw chunks, capture buckets, guard decisions, compulsory and padded rows;
- same-source guard-on versus guard-off causal comparison;
- complete request-time and cost bounds with evidence labels and uncertainty;
- focused offline checks; and
- one real current-runtime H200 consumer command or typed `none`.

A positive terminal prepares one direct current-runtime falsifier for a later
spend decision. It does not reserve spend or authorize provider, GPU,
endpoint, quality, or production work.
