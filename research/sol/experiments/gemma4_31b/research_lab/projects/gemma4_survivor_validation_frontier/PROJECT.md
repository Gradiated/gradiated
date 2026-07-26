# Gemma 4 survivor validation frontier

## Question

Given the campaign's exhausted paid authority, which one preserved
source-complete survivor should receive the next checkpoint, compile, or
target-hardware lifecycle when new authority becomes available, and what is
the smallest falsifier that can change that choice?

Return a scope-correct, evidence-bound validation frontier or typed `none`.
This is not permission to invent another analytical speedup, stack candidates,
or transfer throughput across hardware.

## Why this matters

The lab now has several positive but incomparable survivors:

- exact-model B200 and MI355X placement screens with accelerator-specific
  economic hurdles;
- an exact H100 registered-Attention arm whose scientific sample remains
  unconsumed;
- prompt-state merge, multi-resolution global KV, and recurrent-local
  attention model/runtime candidates with very different target margins,
  fallback tolerances, training requirements, and quality risk.

The current Trainium2 screen is typed `none`: official Neuron source has no
exact Gemma 4 producer/consumer path, so plausible packing and favorable
hypothetical cost rows cannot support a placement claim. With only
`$0.220394` unreserved and no live bench, opening another provider lifecycle
or another geometry-only proxy is lower value than turning the preserved
survivors into a falsifiable next-funding order.

## Bound evidence

- Campaign: `../../CAMPAIGN.md`.
- Exact model configuration:
  `../gemma4_hybrid_attention_placement_codesign/inputs/bound/config.json`
  (`sha256:e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`).
- Exact c32 trace/workload:
  `../gemma4_h200_ngram_fixed_m384_executor_rewrite/inputs/trace/exact_c32_profile.trace.json.gz`
  (`sha256:37e2c73a57e8e63bd7ec0a3465cc1edded8b9dc63507d97e85a767306a97a48b`).
- Qualified denominator: `0.625149101968745 s/request`.
- Locked physical target: `0.500119281574996 s/request`.
- Locked sustainable target: `$0.109725/M total tokens`.
- Prompt-state merge:
  `../gemma4_prompt_token_compaction_codesign/PROMPT_STATE_MERGE_PHYSICAL_SCREEN.json`
  (`sha256:fc87cbfcb3380d4d039f553687e58d5967ace2dd8e4ecc76f97cbe0a2cedbec8`).
- Multi-resolution global KV:
  `../gemma4_multiresolution_global_kv_codesign/MULTIRESOLUTION_GLOBAL_KV_PHYSICAL_SCREEN.json`
  (`sha256:1d7d59a96a50f95b8cbadbb763ee072b5a4c462e1bb03f039dccda3905c84a30`).
- Recurrent local attention:
  `../gemma4_recurrent_local_attention_codesign/RECURRENT_LOCAL_ATTENTION_PHYSICAL_SCREEN.json`
  (`sha256:708761c17bc605702d16058331493c01eab65417d7dc45fdea4a6ea4411fcf87`).
- B200:
  `../gemma4_b200_fp8_runtime_codesign/B200_FP8_RUNTIME_SCREEN.json`
  (`sha256:b6623bf5f4a81002fda5fbd9e34ac7f52af32083c32e8ff657c005850ccc4862`).
- MI355X:
  `../gemma4_mi355x_fp8_runtime_codesign/MI355X_FP8_RUNTIME_SCREEN.json`
  (`sha256:e1bad18d0d2e0d3e281c3502a3b4a25108d0841ac2da85e5fd0fadebe99cc500`).
- H100 pinned-runtime adapter:
  `../h100_hybrid_attention_kernel_mechanism/H100_PINNED_VLLM_CONFIG_REPAIR.json`
  (`sha256:4ebee66bc22f7c88914fa9886175271ccdd822f6ce0d83ea2d6ff51418d9f4c3`).
- Trainium2 negative:
  `../gemma4_trainium2_runtime_codesign/TRAINIUM2_RUNTIME_PLACEMENT_SCREEN.json`
  (`sha256:46a81e09e0a052842e9998dcd662c6ac0a7ce6673f4d391f4525d906b226cf3d`).

## Scope

Work entirely offline and spend `$0`.

1. Verify every bound artifact hash and classify its evidence as measured,
   analytical, source-complete, vendor-reported, inferred, or synthetic.
2. Keep direct placement survivors separate from model/runtime changes. Never
   compare raw seconds across accelerators without the survivor's own
   price-normalized hurdle, and never credit one candidate's savings to
   another.
3. For each survivor, reconstruct:
   - scope and exact consumer reached;
   - target margin and sensitivity boundary;
   - compilation, target-hardware, checkpoint, training, and quality gates;
   - minimum credible falsifier, including setup and cleanup;
   - observation that would immediately close or demote it; and
   - conservative wall-clock, accelerator-hour, storage, and spend envelope
     for that falsifier.
4. Reject inadmissible capacity deletion and favorable arithmetic unsupported
   by a real producer/consumer path. Preserve the conditional-depth result as
   out-of-scope evidence and the Trainium2 result as a current-source typed
   negative; neither may enter the survivor ranking.
5. Rank survivors by decision value per newly authorized dollar and wall-clock
   hour. Penalize tiny analytical margins, unsupported second tiles,
   precision fallback, missing compile paths, new untrained projections, and
   broad quality recovery. Do not treat a source-complete physical bound as
   measured throughput or production quality.
6. Select exactly one primary next lifecycle and at most one offline
   prerequisite. The primary must have a complete reservation-before-create,
   setup, sentinel, measurement, terminal, cleanup, and stop-rule envelope.
   If no survivor can justify new authority, return typed `none` with the
   named missing evidence.

Do not browse for new prices, download the checkpoint, claim hardware,
contact a provider, create resources, implement a candidate, or rerun any
benchmark. Do not reopen Trainium2, tied-head, conditional-depth, pooling, or
closed kernel lineages.

## Decision artifact

Emit `SURVIVOR_VALIDATION_FRONTIER.json` with:

- `classification`: `ranked_validation_frontier` or `typed_none`;
- bound artifact identities and evidence labels;
- separate direct-placement and model/runtime-change ledgers;
- target margin and sensitivity accounting without stacked gains;
- compilation, hardware, checkpoint, training, quality, and production gates;
- per-survivor minimum falsifier, invalidation rule, wall-clock, compute,
  storage, and spend envelope;
- exactly one recommended next lifecycle and at most one offline prerequisite;
- reservation-before-create, sentinel, terminal, cleanup, and stop rules;
- explicit reasons lower-ranked survivors should not consume the next dollar;
  and
- zero-spend resource use.

## What changes the portfolio

A ranked frontier becomes the campaign's next-funding handoff; it does not
authorize provider creation or quality claims. Typed `none` means the
preserved evidence cannot justify another lifecycle without a named external
input such as checkpoint access, target-hardware authority, runtime support,
or training capability.
