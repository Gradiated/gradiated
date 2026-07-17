# H100 current-AWQ c16 economic bound

## Question

Can the exact current GLM-4.7 Flash AWQ/vLLM c16 serving identity plausibly deliver enough H100 SXM throughput to beat the campaign's `$0.514/M` output-token target at the authoritative committed H100 price, and is one matched measurement worth funding?

## Why it matters

The current measured L40S point is 535.286 output tok/s at the exact 8,192-input/1,024-output c16 workload. At the shared `$2.80/H100-hour` planning rate, an H100 must sustain 1,513.186 output tok/s—`2.8269x` the L40S result—to meet `$0.514/M`; the `$2.50–$3.10/hour` sensitivity range requires 1,351.059–1,675.313 tok/s. This is a clean hardware-transfer question, not a rerun of the historical BF16/SGLang H100 result, which changed representation and runtime and therefore cannot answer it.

## Relevant evidence

- `../nebius_current_awq_c16_direct/` provides the measured 535.286-output-tok/s exact current-AWQ L40S c16 control and retained traces.
- `../representation_runtime_bridge/FEASIBILITY_MATRIX.md` identified same-AWQ/vLLM H100 versus L40S as the only prospective one-factor hardware bridge, but predates the current c16 control and campaign economic gate.
- Historical H100 BF16/SGLang served only 305.045 output tok/s at c16; it is a confounded negative prior, not transferable endpoint evidence for current AWQ/vLLM.
- `/root/workspace/research/factory/data/gpu_prices.json` currently binds the H100 SXM planning rate to `$2.80/hour` and the sensitivity range to `$2.50–$3.10/hour`.

## Scope

At zero provider spend, bind the exact checkpoint `/root/.cache/glm47flash-awq-ab31d120` at revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, vLLM 0.15.0 base image `sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543`, derived Transformers revision `1618d44b9295361607ec74d7be860ba886aac039`, `num_kv_splits=4`, `max_num_seqs=16`, cache-off accounting, and the exact c16 8,192/1,024 workload. Hold representation, runtime, tokenizer/request bytes, scheduler intent, and completion envelope fixed; vary only L40S versus H100 SXM.

First prove or falsify exact SM90 load/dispatch compatibility for compressed-tensors W4A16/Marlin and the GLM runtime with a source-bound fixture. Then use retained scope-matched L40S traces, hot-kernel classifications, memory traffic, utilization, and any exact-shape historical H100 evidence to construct conservative bandwidth-, compute-, and scheduling-limited H100 throughput bounds. Apply the current shared price inventory without another web search. Explicitly calculate `$ / M`, the 1,513.186-tok/s base gate, the 1,351.059–1,675.313 sensitivity band, and lifecycle sensitivity.

Do not mutate a provider, allocate a GPU, build a launcher/controller, change representation or runtime, compare against the confounded BF16/SGLang endpoint as if causal, or make a quality/production claim. Prefer an early close if any conservative bottleneck caps H100 below the base gate.

## Resources

- Campaign contract and prices: `../../CAMPAIGN.md` and `/root/workspace/research/factory/data/gpu_prices.json`.
- Current control: `../nebius_current_awq_c16_direct/` and retained current-c16 artifacts under `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.
- Prior causal screen: `../representation_runtime_bridge/FEASIBILITY_MATRIX.md`.
- L40S resource model: `../../hardware/L40S.md`.
- Shared analysis tools: `/root/workspace/research/factory/tools` and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.

## Artifact contract

Produce `h100_current_awq_c16_bound.json`, `source_bound_sm90_fixture.py`, and `RESEARCH_LOG.md`. Label all inputs as measured, derived, vendor-reported, or inferred, and record exact source paths/hashes where available.

## Portfolio-changing result

Nominate at most one future same-identity H100 c16 measurement only if the SM90 fixture passes and a conservative bound reaches at least 1,513.186 output tok/s at `$2.80/hour`, with an explicit matched-arm contract and lifecycle allowance. Otherwise close H100 current-AWQ transfer at `$0` and return capacity to a different hardware, representation, kernel, or serving mechanism.
