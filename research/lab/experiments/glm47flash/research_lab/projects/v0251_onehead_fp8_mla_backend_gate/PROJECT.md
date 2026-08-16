# vLLM 0.25.1 one-head FP8 MLA backend gate

## Decision question

Does the cached upstream vLLM `0.25.1` Triton MLA producer/consumer execute correct and faster FP8 KV on L40S for GLM-4.7 Flash's exact one-KV-head cache geometry, strongly enough to nominate a full47 FP8-c32 integration?

This is materially different from `../sm89_fp8_mla_kv_kernel/`: that home-grown source used 20 KV heads, never launched full attention, and is terminal. Current vLLM source independently adds FP8 KV support to `TritonMLABackend`; this project tests the upstream path itself, not a backport or a generic release A/B.

## Fixed identity and scientific arms

- Cached vLLM `0.25.1` commit `752a3a504485790a2e8491cacbb35c137339ad34` and pinned local image `sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543`.
- Exact geometry: page size 16; one KV head; cache `[pages,16,1,576]`; value alias `:512`; BF16 query/output compute; shuffled page tables; four KV splits; the upstream writer, scales, attention stage, split reduction, and LSE/output consumer must all execute.
- Seed 1234; `B in {1,8,32}`; contexts `8193` and `9215`; matched upstream BF16-cache control then FP8-cache candidate in the same allocation. No 20-head proxy, offline cast, scale fixed to one, or source-only claim.
- Record exact allocated bytes, scale metadata/policy, saturation, output and LSE error against a masked FP32 oracle, dispatch/kernel identities, warmup, p50/p95 writer/stage/full-attention timing, and GPU clocks/power/utilization.

Pass requires finite output, no fallback or saturation, output within `atol=0.03, rtol=0.03`, LSE within `atol=0.10, rtol=0.03`, exact one-head allocated bytes, and at least 10% B32 p50 improvement for stage and full attention with no p95 regression. Static compatibility, imports, compilation, or a candidate kernel that is not invoked are not readiness evidence.

## Provider and lifecycle contract

This is the sole provider-mutation/spend owner. Use the existing absolute shared controller `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py --benchmark-script`; do not create another provider wrapper. Require authenticated zero instance/disk inventory before exactly one preemptible L40S create, a user-systemd owner plus independent cleanup watchdog, at most `$0.55` and 2,100 allocation seconds, exact raw artifacts, and authenticated zero inventory after cleanup. A pre-GPU operational failure is typed operational evidence, not FP8 science, but this project has no unchanged retry.

If measured setup/bootstrap materially exceeds scored GPU time, retain only behind the named trigger `UPSTREAM_ONEHEAD_FP8_COMPONENT_PASS` and only when one content-hashed full47 BF16-c16-control/FP8-c32 integration packet can be made ready within ten minutes using the existing `vllm_recover_existing.py` retained-session path and the same sequential owner/watchdog. Reuse only verified runtime/checkpoint state. If the trigger fails, the packet is not ready, or the controller cannot hand off through that existing path, clean normally. Do not create a second owner or unconditional keep.

Return `UPSTREAM_ONEHEAD_FP8_COMPONENT_PASS`, a typed numerical/performance/runtime close, or an operational-null result with cleanup evidence. A component pass is capacity/kernel evidence and nominates one full47 endpoint; it is not itself an economic or quality pass.

## Why it matters

Correct FP8-plus-scale MLA storage could save roughly `7,561.125 MiB` at c32 and project the full model well below the robust memory convention. Unlike selective W4, it has ample capacity headroom; the unresolved questions are exact upstream SM89 execution, accuracy, and wall time.

## Starting evidence

- `../l40s_mla_full_graph_gate/` (v0.25.1 source support; full mixed-graph question remains separately closed)
- `../vllm_release_delta_screen/` (static exact-model/AWQ compatibility only)
- `../sm89_fp8_mla_kv_kernel/` (invalid custom implementation; do not reuse)
- `../full_model_fp8_kv_c32_corrected/` (v0.15 backend close)
- `../../hardware/L40S.md`
