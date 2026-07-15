# Zero-cost bridge feasibility matrix (2026-07-15)

## Decision

One prospective one-factor bridge is feasible enough to reserve for a later, separately authorized session: **hardware only**, comparing the retained public AWQ checkpoint under pinned vLLM 0.15.0 on an H100 with the retained V21 AWQ/vLLM/L40S control.  It does not authorize a provider run now.

No representation-only or runtime-only result is defensible from the retained endpoint pair.  The endpoint comparison remains a bundled-stack result.

## Inputs and identity facts

| Evidence | Measured fact | Consequence |
| --- | --- | --- |
| V13 H100 artifact | `zai-org/GLM-4.7-Flash@33facc...`; 48 BF16 shards; 62,444,175,504 weight bytes; SGLang runtime; H100 total 81,559 MiB | Native-BF16 endpoint identity |
| V21 L40S artifact | `cyankiwi/GLM-4.7-Flash-AWQ-4bit@ab31d...`; 4 AWQ shards; 20,170,199,928 weight bytes; vLLM 0.15.0; L40S total 46,068 MiB | Public quantized endpoint identity |
| V21 loaded-memory record | 38,985 MiB used of 46,068 MiB under the exact c1/c8 serving configuration | Same AWQ/vLLM configuration has 42,574 MiB more physical H100 memory before any H100-specific runtime overhead |
| V14 SGLang AWQ smoke archive | SGLang started the public AWQ checkpoint on L40S and recorded 18,587 MiB used, but the controller could not retrieve the expected `allocation-result.json`; the retained summary is `FAIL` and contains no fixed-workload/quality result | Compatibility signal only; not a valid runtime control |

The native-BF16 weights alone are 59,551 MiB (binary MiB), exceeding the full 46,068 MiB L40S capacity by 13,483 MiB before runtime or KV cache.  Thus an L40S native-BF16 arm is analytically impossible at any serving geometry.

## Candidate arms

| Factor isolated | Candidate/control | Feasibility | Discrimination | Cheapest falsifier | Decision |
| --- | --- | --- | --- | --- | --- |
| Hardware | AWQ/vLLM H100 versus V21 AWQ/vLLM L40S | Prospectively feasible: exact AWQ revision, vLLM 0.15.0 identity, tokenizer/workload/seed, cache-off intent, c1/c8 geometry, quality diagnostic, and SLO can remain fixed.  H100 has 81,559 MiB versus V21's 38,985 MiB loaded footprint. | Directly estimates the H100-versus-L40S serving effect for this public AWQ/vLLM stack.  A repeated absolute c8 effect of at least 5% is decision-relevant. | Pre-provider image/config capability check must prove the same vLLM 0.15.0 GLM module and compressed-tensors checkpoint load on SM90; then one fixed c1/c8 H100 arm. | **Reserve as only admissible bridge.** It cannot attribute representation or runtime effects. |
| Runtime | AWQ/SGLang/L40S versus V21 AWQ/vLLM/L40S | Conditional but not ready.  It holds public checkpoint and L40S fixed, but requires the GLM-specific SGLang loader patch and a different runtime scheduler implementation.  V14's smoke artifact does not establish the fixed workload, paired quality, or a recovered typed result. | Could estimate a whole-runtime effect only after the patch is part of a pinned runtime identity and both engines meet the common semantic/service contract. | Repair the artifact/result contract locally and run the fixed workload only after the hardware bridge decision and quality/provider gates. | **Do not preregister now.** Treat as a later separate runtime study, not stock-runtime attribution. |
| Representation | Native BF16 versus public AWQ under one runtime/GPU | Not defensible for the endpoint claim.  The checkpoints have different repositories, revisions, shard counts, byte sizes, and no retained content-addressed derivation from the V13 BF16 weights to V21 AWQ weights.  Native BF16 cannot fit the L40S. | Any observed difference combines quantizer/checkpoint implementation with representation, and on L40S also deployment feasibility. | A future independently reproducible, hash-bound quantization transform from the exact V13 revision plus semantic/quality validation. | **Reject for this campaign's endpoint attribution.** |

## Quantified endpoint boundary

V21 measured 355.772 output tok/s at c8; V13 measured 305.045 output tok/s.  The bundled throughput difference is +16.63%.  Their derived endpoint costs are $0.670/M and $3.528/M output tokens, respectively: an 81.01% lower derived cost for the bundled AWQ/vLLM/L40S endpoint.  This arithmetic remains valid only as stated; both endpoints fail the absolute quality screen and the providers/full loaded costs are unmatched.

## Later-session preregistration gate for the hardware bridge

Before any paid execution, require all of the following:

1. New immutable specification whose sole changed field relative to V21 is GPU/platform/price identity; retain the V21 AWQ checkpoint revision and manifest, vLLM image/source identity, tokenizer bindings, seed, exact c1/c8 requests, cache-off setting, generation, quality diagnostic, and SLO accounting.
2. Offline SM90 preflight proving pinned vLLM 0.15.0 recognizes `glm4_moe_lite`, the AWQ compressed-tensors config, and the exact checkpoint manifest; no fallback checkpoint or runtime patch.
3. One H100 session with two randomized or repeated fixed c8 measurements and the V21-equivalent c1 sequence.  Promotion requires both service/semantic gates and a repeatable absolute c8 difference of at least 5%; otherwise report no material hardware effect at this geometry.
4. Preserve utilization, VRAM, power, TTFT, TPOT, queueing, exact server configuration, raw request outcomes, and all-in cost basis.  Carry the absolute-quality failure and prohibit a quality-adjusted business or provider-comparative claim.

## Provenance

- `campaign_100/analysis/OPPORTUNITY_REGISTER_2026-07-14.json` (`OPP-005`)
- `campaign_100/allocations/nebius_h100_complete_stock_v13/preregistration.json`, `summary.json`, and `stock_no_cache_fcfs-artifact.tar.gz`
- `campaign_100/allocations/nebius_l40s_vllm_awq_prefill65k_v21/preregistration.json`, `summary.json`, and `vllm-awq-batch.tar.gz`
- `campaign_100/allocations/nebius_l40s_awq_smoke_v14/preregistration.json`, `summary.json`, and `awq-smoke.tar.gz`
