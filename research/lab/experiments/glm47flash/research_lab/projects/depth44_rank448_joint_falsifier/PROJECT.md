# Depth44 plus rank-448 joint falsifier

## Question

Can a nested 44-layer proxy with MLA KV rank reduced only from 512 to 448 fit the robust L40S c32 envelope and retain a conservative path to `606.355` output tok/s on the authoritative 8K/1K workload?

## Why this matters

The semantics-preserving depth44 memory-tax gate closed because only eager mode saved enough memory and its performance was unbounded. Rank448 is a materially different model/chip co-design: across 44 layers it removes exactly `1,408 MiB` of c32 BF16 KV, moving the current depth44 projection from `45,154.871` to `43,746.871 MiB`, or `785.129 MiB` inside the `44,532-MiB` robust limit. It is also a modest state change explicitly prioritized by the campaign. However, the measured nested depth42-to-depth43 c32 ratio projects depth44 near `589.732` tok/s, and the prior measured MLA transfer raises the optimistic scoped estimate only to about `594.53`, below the robustness gate. A fast joint falsifier should close or nominate this interaction before any checkpoint rewrite or paid arm.

## Fixed evidence

- Depth42 terminal archive `ee0f3f3b3d3abfa2f9610320a5be44934be8493a61f52a0d339e83ca4b3d8541`: c32 `686.910494` output tok/s and peak `43,871 MiB`.
- Depth43 terminal archive `8db63070ed174a9710f181e17d3cb747f9ca70b54775ee6eaf0bfa3beaad8120`: c32 `636.469100` tok/s; exact rank512 depth44 projection `45,154.870758 MiB` is frozen in `../minimal_depth44_runtime_memory_tax_gate/`.
- Exact geometry: rank512 plus 64 rope dimensions uses `288 MiB` of c32 KV per layer; rank448 plus 64 rope dimensions uses `256 MiB`, saving `32 MiB` per layer and `1,408 MiB` across 44 layers.
- Runtime/checkpoint: source revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, group-32 W4A16 compressed tensors, BF16 KV, pinned vLLM `0.15.0`, Transformers `1618d44b9295361607ec74d7be860ba886aac039`, SM89 L40S, cache off, c32, 8,192 input/1,024 output, `max_num_seqs=32`, `max_num_batched_tokens=65536`, and `num_kv_splits=4`.
- Prior rank evidence: `../l40s_model_chip_codesign/` and `../depth_mla_capacity_codesign/`. The latter's inherited student accounting is invalidated; reuse only independently reverified source/tensor-shape facts, never its nomination or memory total.
- Economics: planning `$1.10/hour`, absolute gate `594.466`, robust nomination gate `606.355`, and 300-second background envelope. The current GPU-price inventory is fresh through the seven-day policy.

## Execution contract

Work offline at `$0` for at most 900 seconds, 6 GiB peak RSS, and 24 MiB of new artifacts. Independently reconstruct the 44-layer rank448 KV, payload, and exact `kv_a_proj_with_mqa`/`kv_b_proj` tensor shapes from the source headers and pinned loader. Establish whether one deterministic content-addressed group-32 rewrite and unchanged runtime path is technically coherent, but do not write checkpoint payloads. Recompute the adjacent nested-depth endpoint bound from the raw depth42/depth43 profiles with uncertainty, then apply only scope-matched measured MLA transfer evidence. Treat rank-reduction quality as deferred architecture-cost evidence and do not infer recovery.

Return exactly one terminal result:

- `NOMINATE_JOINT_PROXY`: exact rewrite/loader geometry closes, projected c32 is `<=44,532 MiB`, and a conservative scope-matched endpoint bound is `>=606.355` tok/s with one future c32 falsifier; or
- `JOINT_PROXY_CLOSE`: representation/loader identity fails, robust memory fails, or the conservative endpoint bound is below `606.355` or unidentifiable.

Do not use CUDA, network/provider resources, materialize or mutate a checkpoint, edit shared runtime/launcher code, prepare a controller, train, run quality, or nominate another rank/depth. Produce one compact machine-readable artifact, an optional focused calculator/shape fixture, and a concise research-log update. No successor.

## Available resources

Use the fixed local projects above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
