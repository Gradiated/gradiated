# Recurrent local-attention co-design

## Question

Can the 50 sliding-attention layers in exact Gemma 4 31B replace the
query-by-1,024-key scan with an information-carrying rolling recurrent state
that preserves the full 1,024-token causal horizon, every token contribution,
all 60 layers, and the model's full width, while reducing the locked
`0.625149101968745 s/request` service time to at most
`0.500119281574996 s/request` after every producer, eviction, normalization,
dispatch, fallback, and consumer cost?

This is a quality-unsafe physical discriminator, not a deployable model claim.
It may alter local-attention semantics through a learned feature map or
summary recurrence, but it may not obtain its gain by deleting tokens,
layers, width, parameters, or vocabulary capacity.

## Why this matters

The completed global-KV screen joined the exact c32 trace to the pinned
consumer and separated:

- 750 local sliding calls totaling `997521.149 us`;
- 150 global calls totaling `490684.609 us`; and
- `2375141.908 us` in the complete trace window.

Local attention therefore represents `0.41998381049996614` of that window.
A standalone local mechanism must retain at most
`0.5237911676597444` of the local family, including its new overhead, to close
the locked 20% whole-request gap. That is a demanding but decision-bearing
screen. It is materially distinct from the preserved global-KV candidate:
do not credit global summaries, prompt-state merging, reduced layer depth, a
shorter local window, or any other prior candidate.

## Bound evidence

- Campaign: `../../CAMPAIGN.md`.
- Exact model configuration:
  `../gemma4_hybrid_attention_placement_codesign/inputs/bound/config.json`
  (`sha256:e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`).
- Exact c32 trace:
  `../gemma4_h200_ngram_fixed_m384_executor_rewrite/inputs/trace/exact_c32_profile.trace.json.gz`
  (`sha256:37e2c73a57e8e63bd7ec0a3465cc1edded8b9dc63507d97e85a767306a97a48b`).
- Global/local attribution and source identities:
  `../gemma4_multiresolution_global_kv_codesign/MULTIRESOLUTION_GLOBAL_KV_PHYSICAL_SCREEN.json`
  (`sha256:1d7d59a96a50f95b8cbadbb763ee072b5a4c462e1bb03f039dccda3905c84a30`).
- Pinned runtime source revision:
  `28b095c01005d4a3a2a5b637b7d028b07fba31b2`.

The relevant exact geometry is 50 sliding layers, 16 KV heads, 32 query
heads, head dimension 256, a 1,024-token window, and 12 TARGET_VERIFY query
rows per request at c32.

## Scope

Work entirely offline and spend `$0`.

1. Reconstruct the pinned local-attention producer and first real consumer,
   including RoPE position semantics, GQA head mapping, causal masks, request
   ownership, graph padding, and rolling-window eviction.
2. Implement a source-complete rolling state path through that consumer. A
   plausible form is a positive-feature recurrent numerator/denominator with
   blockwise subtractive eviction, but choose the representation from the
   exact geometry and source. Every token entering the 1,024-token horizon
   must mechanically contribute to retained state until it expires.
3. Preserve all local layers, hidden width, heads, parameters, query rows,
   and the exact 1,024-token horizon. A selector, shorter window, fixed token
   drop, or relabeled width/layer reduction is an invalid attempt.
4. Charge feature projection, state update, block materialization, eviction,
   normalization, metadata, graph variant, request/position validation,
   fallback, and the real output consumer. Include state bytes and a
   conservative accelerator cost model; peak-FLOP or bandwidth transfer alone
   is not evidence.
5. Compare the full candidate local-family cost with the exact trace. Emit
   sensitivities for feature rank/state size, block boundary handling,
   non-scaling overhead, and fallback. Do not sweep aimlessly: identify the
   smallest geometry whose one-pass consumer can physically fit, and fail
   closed if a second pass destroys the target.
6. Prove the information path with a deterministic CPU fixture when practical:
   every in-window token contributes exactly once, expired tokens contribute
   zero, protected/current positions are not double-counted, and output
   shapes and finite-value invariants hold. Lack of Torch/CUDA is a limitation,
   not permission to assert an unexecuted consumer.

Do not download checkpoint bytes, claim a GPU, contact a provider, run broad
quality evaluation, or stack another candidate's savings.

## Decision artifact

Emit `RECURRENT_LOCAL_ATTENTION_PHYSICAL_SCREEN.json` with:

- `classification`: `source_complete_physical_candidate` or `typed_none`;
- bound input and source hashes;
- exact global/local trace attribution and the `47.62088323402555%` required
  local-family reduction;
- implemented producer, state, eviction, and real-consumer paths with source
  hashes;
- a mechanical information-path and capacity-exclusion audit;
- full physical accounting, sensitivities, and derived whole-request service
  time;
- explicit quality, compilation, measurement, and transfer limitations; and
- zero-spend resource use.

Return a candidate only if the complete standalone path reaches
`0.500119281574996 s/request` conservatively. Otherwise return typed `none`
and identify the binding floor. A favorable metric from token selection,
window shortening, layer/width deletion, omitted state production, or an
unconsumed metadata hook is invalid.

## What changes the portfolio

A source-complete candidate becomes a quality-unqualified target-GPU
measurement candidate when authority returns. Typed `none` closes this exact
rolling-recurrence representation and redirects the portfolio away from
local-attention state compression; it does not negate the preserved global-KV
or prompt-state candidates.
