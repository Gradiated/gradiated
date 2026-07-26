# Gemma 4 conditional-depth codesign

## Question

Can request- and phase-adaptive execution of contiguous Gemma 4 transformer
blocks remove enough real c32 prefill and verification work to reduce the
qualified `0.625149101968745 s/request` service time to the locked
`0.500119281574996 s/request` target, after routing, graph, and residual
overheads?

This is a model/runtime co-design hypothesis. It is distinct from static
full-versus-sliding attention placement: the checkpoint geometry remains the
60-layer Gemma stack, while an explicit router selects executable block groups
for a request or phase. The first result is a quality-unsafe physical proxy,
not a production model.

## Bound evidence and scope

- Model: `google/gemma-4-31B-it` at revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Workload: text-only, non-reasoning c32 traffic around 4,214 prompt and 358
  output tokens per request.
- Qualified baseline: `0.625149101968745 s/request`.
- Locked target: `0.500119281574996 s/request`.
- Exact model geometry:
  `../gemma4_hybrid_attention_placement_codesign/inputs/bound/config.json`,
  SHA-256
  `e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`.
- Trace-backed per-layer physical reconstruction:
  `../gemma4_hybrid_attention_placement_codesign/PLACEMENT_SIMULATION_RESULT.json`,
  SHA-256
  `2af53085953393785204eafb2c2dd0e9d335805f8a8e5963ae46fb57ed99e40b`.
- The completed capacity-pooling screen proves that scheduling alone cannot
  close the target: even its perfect-utilization GPU-only floor remains above
  the economic target and still requires a 20% measured service reduction.
- The static all-local attention ceiling in the bound placement simulation is
  only about 10.1--10.7%; conditional depth must remove attention, projection,
  MLP, normalization, quantization, and launch work rather than relabel that
  result.

Do not transfer B200, MI355X, H100, peak-FLOP, or unrelated-model speed
claims. Do not infer semantic quality from timing geometry.

## Immediate evidence path

1. Reconstruct non-overlapping c32 prefill and target-verification cost by
   transformer block and operation family from the bound measured evidence.
   Preserve an explicit non-skippable residual.
2. Enumerate a small set of executable phase-specific schedules using
   contiguous block groups. Account for router execution, graph variants,
   compaction, synchronization, KV ownership, and any work that remains even
   when a block is bypassed.
3. Inspect the pinned Gemma/runtime layer loop and identify the exact producer
   and consumer symbols where a block group can be bypassed without
   materializing skipped QKV, MLP, normalization, or dynamic-FP8 work.
4. Implement a deterministic schedule/cost discriminator and the smallest
   source-complete reference intervention or patch. It must prove that the
   nominated schedule actually removes the counted launches and tensor work;
   a mask that still executes every block is negative.
5. Report the required active-layer fraction separately for prefill and
   verification/decode, conservative service time after all modeled overhead,
   sensitivity to routing error and graph fragmentation, and the exact later
   quality-recovery path. A viable recovery path may use distillation or
   continued training, but no unmeasured accuracy credit is allowed.

The researcher may replace the proposed routing rule with a sharper one, but
must retain the exact model/workload target and the physical falsifier.

## Terminal

Write `DYNAMIC_DEPTH_PHYSICAL_SCREEN.json` as exactly one of:

- `source_complete_physical_candidate`: an executable layer-loop
  intervention and schedule has a conservative trace-backed bound at or below
  `0.500119281574996 s/request` after router, graph, synchronization, and
  non-skippable residual costs; or
- `typed_none`: the required active depth, unavoidable residual, runtime
  execution semantics, or overhead cannot meet the locked target, with the
  strongest attainable bound preserved.

Planning prose, a nominal FLOP count, a generic early-exit survey, or a patch
that does not remove the counted runtime work is not a terminal. Any positive
terminal remains quality-unsafe and unmeasured until separately authorized
checkpoint recovery and scope-matched GPU/quality evaluation.

## Budgets

- Wall clock: 150 minutes.
- Compute: at most 12 local CPU-hours; zero accelerator compute.
- Storage: at most 4 GiB of new durable artifacts.
- Provider spend: `$0.00`.
- Checkpoint download, provider contact or mutation, and GPU claims are
  forbidden.
