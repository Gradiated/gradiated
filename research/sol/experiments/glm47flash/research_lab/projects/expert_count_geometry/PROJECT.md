# Expert-count and grouped-MoE geometry

## Question

Can fewer routed experts, with top-k chosen jointly rather than reduced in isolation, improve GLM-4.7 Flash's c16 L40S grouped-MoE realization enough to support at least 10% lower sustainable cost or a cheaper placement?

## Why it matters

The exact c16 stock geometry creates only 64 routed token-expert assignments per MoE layer: 16 active rows times top-4 across 64 experts, or one row per expert on average, spread over 142 SMs. The checkpoint has 64 routed experts per sparse layer and each exact AWQ expert occupies 5,308,464 bytes. A 16-expert layer is therefore about 81 MiB and can fit in the L40S's 96 MiB L2, while the stock layer cannot. The closed top-2 experiment reduced assignments and risked making tiny expert groups worse; it never tested fewer/merged experts that increase rows per active expert and shrink the layer working set.

## Scope

At zero provider spend, reconstruct the exact loaded sparse-layer identity, routing and expert tensor geometry from the current AWQ checkpoint and pinned vLLM path. Compare only a small joint set such as stock `64 experts / top-4`, `32 / top-4`, and `16 / top-4`, adding one different top-k only if it discriminates compute reduction from fragmentation. For each, derive the c16 active-expert `M` distribution under uniform, balanced, and checkpoint- or trace-grounded skew; expert-weight hot set, L2 fit, routed parameters, active FLOPs, routing metadata, grouped-GEMM grids/waves over 142 SMs, and c16/c32 memory implications.

Build the smallest source-bound executable architecture-cost proxy or synthetic exact-shape fixture needed to establish the proposed dispatch and tensor shapes. It may merge, select, or synthesize expert groups and is explicitly semantics-changing; report the implied parameter/capacity loss and whether modest distillation or recovery is plausible. Do not alter shared experts, layer depth, MLA ranks, precision, output head, scheduler, or the shared provider launcher. Do not run a GPU, train, or perform general quality evaluation.

Calibrate any endpoint claim against the retained L40S c16 result and trace transfer; summed kernel duration is not wall time. A cache-fit observation alone is not a speed result. Identify the one minimal target-GPU measurement and counters that would decide between underfilled grids, weight traffic, and routing overhead if a candidate survives.

## Resources

- Current control: 535.286 output tok/s and about `$0.571/M` at the fresh `$1.10/L40S-hour` planning rate.
- Exact AWQ checkpoint: `/root/.cache/glm47flash-awq-ab31d120`.
- Exact tensor inventory: `../moe_expert_offload_bound/CORRECTED_RESULT.json`.
- Retained MoE trace ceiling: `../adaptive_moe_architecture/artifacts/ADAPTIVE_MOE_C16_PROXY_2026-07-15.json`.
- Shared chip dossier: `../../hardware/L40S.md`.
- Runtime and trace artifacts: `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.

## Portfolio-changing result

Nominate at most one expert-count/top-k geometry only if it has a source-bound executable proxy, a conservative path to at least 10% lower c16 cost or a real batch/cheaper-chip discontinuity, and a plausible recovery story. The nomination must state the exact future L40S A/B and minimal physical counters. Otherwise close expert-count reduction rather than requesting a broad profiler or training project. This project has no provider authority or spend.

## Director scope correction — Cycle 38

The checkpoint header contains `model.layers.47.*`, but the config also declares `num_hidden_layers=47` and `num_nextn_predict_layers=1`: layer 47 is the separate MTP payload, not a 47th sparse layer in the stock serving graph. Current serving has dense layer 0 plus 46 MoE layers 1–46. The project's per-layer 16-expert L2 fit, c16 group-M geometry, and 16/top-2 trace ceiling are unchanged; its routed-checkpoint totals overcount stock serving by one MTP expert set. The close decision stands.
