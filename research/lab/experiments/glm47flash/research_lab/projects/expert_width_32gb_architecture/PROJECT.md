# Expert-width / 32 GB architecture co-design

## Question

Can a tile-aligned reduction of both routed and shared MoE intermediate width preserve GLM-4.7 Flash's 64-expert/top-4 execution structure while either lowering L40S c16 cost by at least 10% or unlocking an economical exact 32 GB placement?

## Why it matters

The exact checkpoint uses MoE intermediate width 1,536 across 46 serving MoE layers, with 64 routed experts, top-4 routing, and one shared expert. Retained lower trace shares attribute 12.374% to fused routed MoE, 6.7166% to standard Marlin, and 0.3844% to the shared residual, for a deliberately optimistic combined expert-path ceiling of about 19.475%. Width 1,024 can therefore save at most about 6.49% of endpoint time and width 768 at most about 9.74%, both below the campaign gate. Width 512 saves two thirds of expert work and has a roughly 12.98% ideal endpoint ceiling, so it is the only candidate that survives the first screen.

The checkpoint's routed expert weights are about 14.871 GiB and shared expert weights about 0.826 GiB. Reducing both widths from 1,536 to 512 would remove roughly 10.46 GiB before allocator, padding, and KV interactions. Against the measured c16 peak near 43.07 GiB, that is large enough to investigate a real 32 GB placement rather than only a theoretical FLOP reduction. The current inventory includes a 32 GB RTX 5090 with 1,792 GB/s memory bandwidth and 170 SMs, but exact runtime support and sustainable committed economics are unbound.

This is explicitly semantics-changing architecture-cost evidence. Any promoted design will need recovery training and quality evaluation later.

## Scope

At zero provider spend, bind the exact config, safetensors headers, compressed-tensors W4A16 group-32 representation, serving depth, and retained c16 trace identity. Compare only intermediate widths 1,024, 768, and 512, treating 512 as the primary candidate and the others as calibration points. Keep routed expert count 64, top-k 4, one shared expert, layer depth, MLA geometry, precision, batching, and scheduler fixed.

For each width, derive routed and shared weight bytes including packed weights and scales, active token FLOPs and bytes, exact gate/up/down matrix shapes, group-32 legality, checkpoint/config/loader changes, and c16 memory admission. Construct a source-bound synthetic exact-shape fixture that proves the proposed tensor representation and loader/config contract without transforming the full checkpoint.

Map the exact grouped-GEMM grids, tiles, and waves to the L40S's 142 SMs, 96 MB L2, and Ada tensor-core geometry. Independently test whether the same architecture has an exact 32 GB execution and memory path on the strongest current 32 GB candidate, initially RTX 5090 with 170 SMs and SM120. Fail closed on missing W4 runtime support, capacity, or a sustainable all-in rate. Refresh only the missing candidate-specific rate if the exact placement/runtime screen passes; do not repeat a broad hardware or pricing survey.

Calibrate endpoint claims against the measured 535.286 output tok/s L40S c16 control and the campaign's planning gate of 594.466 output tok/s. Summed trace work is an ideal ceiling, not wall time. State conservative transfer bounds, allocator/KV uncertainty, and the one minimal future L40S or 32 GB GPU measurement and physical counters that would falsify the candidate.

Do not transform the full checkpoint, train or distill, run a GPU, mutate a provider, edit the shared launcher, or perform general quality work. Do not turn the 1,024 and 768 controls into independent projects.

## Resources

- Campaign control and economics: `../../CAMPAIGN.md` and `../nebius_current_awq_c16_direct/`.
- Exact AWQ checkpoint: `/root/.cache/glm47flash-awq-ab31d120`.
- Routed-expert geometry and trace transfer: `../expert_count_geometry/` and `../adaptive_moe_architecture/artifacts/ADAPTIVE_MOE_C16_PROXY_2026-07-15.json`.
- Corrected checkpoint accounting: `../moe_expert_offload_bound/CORRECTED_RESULT.json`.
- L40S dossier and shared accelerator inventory: `../../hardware/L40S.md` and `/root/workspace/research/factory/data/`.
- Shared experiment tooling: `/root/workspace/research/factory/tools` and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.

## Portfolio-changing result

Nominate at most one later executable proxy only if a source-bound exact-shape fixture passes and either (a) conservative transfer supports at least 10% lower sustainable L40S cost, or (b) an exact 32 GB runtime and memory placement has sustainable all-in economics below the campaign target. The nomination must specify one bounded matched GPU measurement, exact output identity, and discriminating kernel/memory counters. Otherwise close width reduction without checkpoint conversion, training, or provider spend.
