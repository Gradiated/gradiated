# Research log

No researcher result yet. Screen widths 1,024/768/512 at zero provider spend, focus on the only ideal-gate survivor (512), and return an exact-shape cost/placement falsifier rather than a checkpoint conversion or training plan.

## 2026-07-15 — Exact-shape fixture and capacity falsifier: close

Question/action: bind widths 1,024/768/512 to the exact AWQ headers and test the 512 candidate against the L40S economic gate and RTX 5090 32 GB placement. Built `source_bound_width_fixture.json` from config SHA `079f8f...fa7622b9`, index SHA `b9c534...988695`, and a parsed safetensors header; no checkpoint shard was transformed, no GPU/provider was used, and no price refresh was authorized after the placement screen.

Evidence: the live checkpoint has 47 sparse layers (IDs 1..47), 64 routed experts, top-4, and one shared expert. W4A16 group-32 shapes are legal for every tested width: gate/up packed `[W,256]`, down packed `[2048,W/8]`, gate/up scales `[W,64]`, and down scales `[2048,W/32]`; shared BF16 matrices use the same W dimension. At W=512, routed weights are 4.957 GiB, shared weights 0.275 GiB, and active routed+shared expert work is 31.46M FLOPs per MoE layer. Widths are exact 128-output-tile multiples (4/6/8/12 tiles), but decode c16 has about one row per expert; only prefill has 512 uniform rows/expert.

Interpretation: the current 43.07 GiB peak minus the W=1536→512 expert-weight reduction of 10.4648 GiB projects to 32.6052 GiB before allocator/KV headroom. That fails a nominal 32 GiB RTX 5090 placement, even before the exact W4 runtime path is proven; 5090 has 170 SM, 32 GB GDDR7, 1,792 GB/s, but no project-bound sustainable price and the inventory marks software maturity current_non_datacenter. On L40S, a conservative credit of only explicitly attributed fused routed (12.374%) plus shared residual (0.3844%) gives 8.506% endpoint ceiling at W=512, below the 9.955% required wall-time reduction / 594.466 tok/s gate. Crediting unassigned standard Marlin would be an optimistic ceiling, not evidence.

Decision/next move: close width reduction without checkpoint conversion, recovery training, GPU execution, or provider spend. Reopen only if a future measurement demonstrates at least 0.606 GiB of additional peak reduction plus headroom on an exact 32 GB path, or provides a new runtime/placement with a measured matched control. The only useful future counters are endpoint throughput, allocator peak/KV residency, grouped-GEMM M/N/K tiles and waves, register/shared occupancy, L2 hit, and DRAM bytes.
