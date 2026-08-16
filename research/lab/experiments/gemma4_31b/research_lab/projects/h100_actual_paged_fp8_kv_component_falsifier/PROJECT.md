# H100 actual paged FP8-KV component falsifier

## Decision question

Does FP8 E4M3 KV through the exact pinned image's actual cache producer and selected paged-attention backend reduce H100 memory traffic and attention time enough to save at least 5% of the campaign request service budget?

This is a checkpoint-free semantics-changing cost-mechanism proxy. A pass does not establish endpoint throughput, deployable quality, reliability, fit, or economic acceptance.

## Authoritative inputs and identity

Consume without rewriting:

- `../post_l40s_fp8_successor_selection/SELECTION.json` SHA-256 `f94e40c4d63d67a939d0b6c8fa855a995cff06d66b254cbf8a41727ecaf2d326`.
- `../h100_hybrid_attention_kernel_mechanism/MECHANISM.json` SHA-256 `3960c453e88b1a12e01351d2062dbaa7f8a800e63fe6674e997ddbbcfeebdda1`.
- `../exact_geometry_runtime_opportunities/GEOMETRY.json` SHA-256 `024450cd944c7827db442d8274e1e0cccae114ee3bbb2e0473704f2fbf0e3a72`.
- `../exact_bf16_mtp_h100_frontier/artifacts/preflight-20260717T000000Z/hf-config.json` SHA-256 `e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1`.
- `/root/workspace/research/factory/data/accelerator_inventory.json` SHA-256 `bcb33ac6814400f6ab79faa7e44c0ced2d6fe2ac5d19dc43f4ee10b12d7ea6b8`.
- `/root/workspace/research/factory/data/gpu_prices.json` SHA-256 `3f403d67a92fc91be85bbd27dede85f5f91c3fd2df25ef8dcef2a344acbd1e01`.

Execution identity is model geometry `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4` and immutable image `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, observed vLLM `0.19.1.dev6+g6d4a8e6d2`, on one full NVIDIA H100 SXM, TP=1. The mechanism's upstream source revision `ab0a20d15129b322f911db578b50c6b35b3167e7` is an analytical prior, not execution-equivalent to the image. The first paid sentinel must record and bind the installed image's exact producer/backend source hashes, constructor/signature, selected local/global backend classes, and supported FP8 paths; mismatch with required semantics stops and cleans rather than spawning a source-binding successor.

`assert_identity.py` mechanically recomputes all authoritative hashes and checks that this brief matches the selection. It must pass before any provider access.

## Execution contract

Use `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py` through one lowercase user-systemd durable owner and one sequential `placement_control.VerifiedRetainedOwner` watchdog. The owner is exclusive for provider query, mutation, and spend. One preemptible `gpu-h100-sxm / 1gpu-16vcpu-200gb` instance plus one 100-GiB network disk; one create; zero repair/restart; no checkpoint.

Before create, render and behaviorally audit the complete primary, conditional, counter-capture, owner, watchdog, trigger, accounting, and cleanup bytes. Require exact immutable inputs, image, H100 request, credentials, authenticated empty inventory, writable artifact root, and deadline in one typed terminal. CUDA-only producer/backend construction is the first atomically retrieved fail-fast stage, not an offline readiness gate.

The primary stage must retrieve both matched arms at:

- local c8, context 1024, 32 query heads, 16 KV heads, head dimension 256;
- global c8, context 4214, 32 query heads, 4 KV heads, head dimension 512.

For each arm invoke installed `unified_kv_cache_update` with deterministic varied-sign nonzero K/V, then the actual selected paged backend using `block_table`, `slot_mapping`, and `seqused_k`. Dense-varlen or direct-kernel stand-ins fail. Consume outputs and require FP8 versus BF16 cosine similarity `>=0.99` and normalized RMSE `<=0.05`. Record BF16/FP8 timing and actual measurable DRAM/L2/cycles/warps/launch counters over the same NVTX attention range. If named counters are unavailable, return a typed sentinel failure and clean; do not silently weaken the mechanism gate.

Conditional sweep runs only after both retrieved sentinel rows pass exact identity/backend/oracle plus FP8 p50 interval-union time `>=10%` lower, DRAM reads `<=60%` of BF16, unchanged launch count, and at least seven provider minutes remain. Sweep c8/c16/c32 at local context 1024 and global contexts 4214/4393/4571 with 20 warmups and 100 randomized paired repetitions, alternating arm order. Acceptance additionally requires context-scaled byte reduction and architecture-weighted measured saving across 50 local and 10 global layers over 358 decode steps of at least `0.027398761575976767 s/request`.

## Adjacent retained-session arm

Prepare the exact-image H100 direct-linear arm fully offline before create if it can be start-ready within ten minutes. Run it sequentially on the same retained image/session only under named trigger `H100_FP8_KV_PRIMARY_PASS_AND_SETUP_DOMINATES`: both sentinel rows pass every identity/oracle/component/mechanism gate; measured bootstrap plus image setup exceeds scored primary GPU time; at least seven provider minutes remain; and its immutable program is already staged. It fresh-matches BF16 matmul versus actual `cutlass_scaled_mm` FP8 at the six exact Gemma fused-linear shapes for M=8/16/32 and M=3679 using the corrected dual oracle. It may report architecture-weighted H100 linear saving separately but cannot inherit L40S timing/admission. If any trigger clause fails, clean immediately. No endpoint, checkpoint, MTP, prefix-cache, W4, or compilation retention.

## Budgets and terminal

- Wall clock: 40 minutes.
- Provider exposure: 25 minutes.
- Compute: 0.35 H100 GPU-hours plus 2 local CPU-hours.
- Storage: one 100-GiB provider disk; 512 MiB retained plus 2 GiB temporary local.
- Spend: `$1.30` maximum; one allocation; zero repair/restart.

Stop and clean on identity/image/source-symbol/backend mismatch, actual producer/consumer construction failure, oracle failure, missing atomic sentinel retrieval, invalid counter/timing range, sentinel threshold failure, deadline reserve below seven minutes, or any budget violation. After one valid sweep and optional triggered linear arm, evaluate once and clean. Terminal acceptance requires typed retrieved artifacts, exact exposure/useful-GPU/cost accounting, watchdog identity, and authenticated zero instances/disks.
