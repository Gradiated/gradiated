# B200 runtime-FP8 hybrid-attention dataflow

## Question

Can one exact, semantics-preserving decode intervention in Gemma 4's
five-local/one-global attention and KV-cache dataflow remove enough recurring
launch, metadata, or memory traffic on SM100 to justify a B200 component
measurement, independently of the active M32 FP8-GEMM dispatcher change?

## Why this matters

The valid absolute B200 runtime-dynamic-FP8 c32 endpoint is
`0.633995593312477 s/request`, still above the fixed
`0.500119281574996 s/request` campaign target. The active paid lane targets
M32 scaled-MM dispatch, while the completed cross-operator analysis found that
the pinned runtime already fuses RMSNorm with dynamic-FP8 quantization. Gemma's
60-layer five-local/one-global structure instead exposes a materially
different recurring boundary: local d256/window-1024 and global d512
attention, page-table and sequence metadata, KV reads/writes, and the
transition between local and global layers.

## Authoritative evidence

- Exact model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Exact runtime image:
  `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`
  at vLLM commit `6d4a8e6d204a9b2827544003b26321fff62923da`.
- Valid comparator:
  `projects/gemma4_b200_dynamic_fp8_endpoint/artifacts/b200-dynamic-fp8-repair2-20260728t1517z/FINAL_TERMINAL.json`,
  SHA-256
  `2873d1b8d311153e903aeb525d59cd61620ecc1129120cfc81e2ec1f5d68ae86`.
  Use only its absolute dynamic-FP8 c32 result; its BF16 and paired-delta
  fields are invalid.
- Exclusion/accounting references:
  `projects/gemma4_b200_fp8_residual_hotpath/B200_FP8_RESIDUAL_DISCRIMINATOR.json`
  and
  `projects/gemma4_b200_fp8_cross_operator_executor/B200_FP8_CROSS_OPERATOR_DISCRIMINATOR.json`.

## Scope

Use `$researcher` with the deep profile and `$kernel-research`. Read this
brief, the three named artifacts above, the exact Gemma configuration, and
only pinned vLLM source needed to follow the production decode attention and
KV path.

Reconstruct the exact local/global layer counts, query/KV head geometry,
head dimensions, cache dtype/layout, block/page geometry, and c32 decode call
counts. Produce non-overlapping launch, byte, and source-symbol accounting for
one recurring attention/KV hot block. Then do one of:

1. implement and hash-bind one production-input-to-first-consumer source patch
   or lifecycle-pure exact consumer with a correctness oracle and a predicted
   SM100 counter change; or
2. persist a typed mechanism rejection showing why the cheapest exact
   intervention cannot remove meaningful work or cannot preserve semantics.

Promising boundaries include local-window page traversal, repeated attention
metadata construction, unified global-K/V reuse, cache layout/conversion, or a
fused exact local-attention dataflow. These are leads, not required choices.
Prefer an existing pinned-runtime primitive when it covers the semantics.

Do not modify `cutlass_gemm_sm100_fp8_dispatch`, scaled-MM tile selection,
RMSNorm/dynamic-FP8 fusion, the output head, or speculative decoding. Do not
claim a bench, run CUDA, replay an endpoint, mutate the active B200, or perform
provider operations.

## Artifact and decision

Write `B200_FP8_HYBRID_ATTENTION_DISCRIMINATOR.json`. It must bind exact source
and implementation identities, correctness semantics, workload-weighted
calls/bytes/launches, non-overlap with both completed analyses, and the
smallest real B200 component command.

A working exact-consumer intervention with a credible endpoint relevance
earns a later component reservation and warm-bench decision. A typed rejection
closes only the selected attention/KV boundary and must identify the next
materially distinct boundary, not prescribe another planning project.

## Budgets

- GPU/provider spend: `$0`
- Wall clock: `90 minutes`
- Storage: `1 GiB`
- Endpoint requests: `0`

## 2026-07-28 continuation — local-window page traversal and KV append

The global K=V projection-elision discriminator is complete and retained for
a later B200 component. Continue this same hybrid-attention project at the
materially distinct boundary it identified: the 50 local layers' recurring
window-1024 page traversal, slot mapping, KV append, and first local-attention
consumer across the exact c32 decode workload.

Use `$researcher` with the deep profile and `$kernel-research`. Read
`B200_FP8_HYBRID_ATTENTION_DISCRIMINATOR.json` once, then inspect only the
relevant pinned vLLM/FlashInfer source. Bind the exact HND paged-KV layout,
BF16 cache dtype, 16-token local blocks, 64–65 intersecting pages, 17,900
local attention and append calls, CUDA-graph padding/no-op semantics, producer
and first consumer, and non-overlapping bytes/launches. Produce
`B200_FP8_LOCAL_WINDOW_KV_DISCRIMINATOR.json` with one hash-bound
production-input-to-first-consumer implementation and correctness oracle, or
a typed mechanism rejection.

Do not claim a bench, run CUDA, replay the prior contiguous-local-KV layout
candidate, modify the active M32 dispatcher, modify the retained global K=V
patch, replay an endpoint, or perform provider operations. The budgets remain
zero GPU spend, 90 minutes, 1 GiB storage, and zero endpoint requests.

## 2026-07-28 continuation — paid global K=V discriminator

The local-window compaction boundary is rejected, while
`B200_FP8_HYBRID_ATTENTION_DISCRIMINATOR.json` retains a hash-bound,
semantics-preserving TP=1 global K=V projection-elision candidate. Promote
that existing candidate to one B200 component question without reopening
source discovery.

After a durable project reservation and a fresh director lifecycle handoff,
use `$researcher` with the execution profile and `$kernel-research`. Reuse the
exact pinned image, checkpoint, candidate source, patch, and component runner.
Materialize one hash-bound M32 production hidden capture from the retained
exact checkpoint if it is not already present, then run the prescribed stock
and candidate global-QKV projection distributions through the unchanged first
attention consumer. Persist loaded weights, hidden capture, source, extension,
backend, output, and timing identities.

Do not claim a bench before the director marks it ready, change the candidate,
touch the M32 dispatcher or local-window compaction, or replay an endpoint.
The component may consume at most one paired stock/candidate measurement
generation. Budget: `$2` cumulative provider spend, 30 minutes claimed B200,
2 GiB additional storage, and zero endpoint requests.
