# Minimal-change c32 model/chip co-design

## Question

If the exact full-model runtime cannot make c32 useful on L40S, what is the smallest executable change to the 47-layer model representation or architecture that creates robust c32 headroom and has a conservative throughput/cost path?

## Why it matters

The complete current-AWQ c32 estimate is only 807.7 MiB above the physical envelope, so removing eight layers is much more divergence than capacity alone requires. We should identify the nearest-to-original intervention before investing in recovery training. Candidate mechanisms must be derived from exact tensors and L40S realization, not nominal parameter counts.

## Fixed evidence

- Preserve all 47 serving layers, routing topology, vocabulary, tokenizer, workload, and current W4 routed-expert representation unless the nominated mechanism explicitly changes one field.
- Current c32 projects to 46,875.7 MiB versus 46,068 MiB. Robust admission should target at least 1.5 GiB post-allocation headroom rather than merely crossing zero.
- Stock MLA uses `kv_lora_rank=512`; reducing latent state affects every token/layer and can alter both KV capacity and grouped-MLA tile/shared-memory legality.
- The ignored BF16 residual contains approximately 605 MiB output head, 828 MiB shared experts, and 161.5 MiB dense layer-0 linears. Full native W4 would save about 1,146 MiB, but layer-0 KV-A `[576,2048]` lacks the prior conservative Marlin tile path; head and shared scopes are independently shape-legal, while the pinned loader lacks an exact mixed checkpoint path.
- Training and full quality are deferred. A proxy may alter semantics, but it must be labeled and measure the cost mechanism.

## Scope

Consume the prior rank/tile, residual-W4, selective-FP8, and depth artifacts as fixed evidence; do not rerun their broad screens. Compare at least three genuinely minimal candidates using exact checkpoint headers, runtime source, and L40S geometry:

1. rank-384 MLA as the clean capacity control: it projects about 2.20 GiB c32 headroom, but prior shape divisibility is not a loader/compile pass and its inferred endpoint upside is far below 594.466 tok/s;
2. rank-448 plus head/shared-residual W4 as the smallest interaction worth falsifying: the rank change makes KV-A's output dimension 512, while the combined memory projection only narrowly clears the 1.5-GiB headroom rule and neither rewritten loader path is proven; and
3. the smallest physical-depth AWQ fallback that can both robustly admit c32 and clear 594.466 tok/s under a conservative work bound, using the already-proven student39 materializer/loader route rather than inventing a new checkpoint format. Five removed blocks are the prior optimistic 10.42% boundary; determine whether that or a nearby pattern is the minimum executable divergence.

For each, quantify changed tensors/bytes, c32 capacity, per-token traffic/FLOPs, tensor-core and shared-memory tile legality, loader/kernel path, likely critical-path effect, and required throughput to beat the matched c16 economics. Reject changes that only fit memory but predict no useful c32 throughput path. Use existing artifacts rather than repeating broad scans.

Implement the strongest candidate as a content-addressed executable proxy at `$0`: rewrite/slice only the required tensors and config, or build an exact-shape kernel proxy when a full checkpoint rewrite would add no decision value. A shape microbenchmark is not checkpoint-loader evidence; quarantine the inherited rank-loader claim until an actual rewritten checkpoint loads. Run focused local loader/source and shape checks. Do not train, evaluate quality, allocate a provider, edit the shared paid launcher, or materialize multiple checkpoints. Nominate exactly one later L40S arm only if the proxy proves a real loader/kernel route, at least 1.5 GiB projected headroom, and a conservative path to 594.466 output tok/s at `$1.10/hour`.

## Portfolio decision

A passing candidate becomes the next measured L40S arm only after the near-stock project classifies exact-model c32. If exact-model c32 succeeds, retain this as comparative opportunity evidence and do not spend automatically. If no minimal candidate passes, report that c32 requires a larger model change or different hardware and redirect the portfolio rather than weakening the gate.

## Artifact contract

Produce one ranked exact-tensor comparison, one executable proxy for the winner, focused verification, a compact nomination or closure decision, and a concise `RESEARCH_LOG.md`.
