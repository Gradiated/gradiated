# Exact EAGLE3 compressed-vocabulary bridge

## Question

Does `thoughtworks/GLM-4.7-Flash-Eagle3` contain a deterministic, target-verifiable 32k-to-154,880 token bridge compatible with the exact campaign AWQ target and pinned vLLM, and can that one-layer draft robustly fit and clear `606.355` output tok/s on L40S c16?

## Why this matters

The broad external-draft gate stopped because the candidate's `draft_vocab_size=32000` and BOS/EOS IDs differ from the target. That is a valid translation-free identity failure, but not yet a scientific closure of EAGLE3: compressed-vocabulary EAGLE implementations may carry an explicit draft-to-target mapping and still verify every accepted token with the target. This candidate is exact-model-specific and its public card reports `54.9%` acceptance and `1.66x` speedup on H200. Those figures are not transferable to L40S or this workload, but they make the mapping semantics worth one narrow audit before discarding the only learned exact-model draft lead.

## Fixed evidence

- Target: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, manifest SHA-256 `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`, vocabulary `154880`, BOS `0`, EOS `[154820,154827,154829]`.
- Draft: `thoughtworks/GLM-4.7-Flash-Eagle3@c43b5f18f59b8fba69e8c0d585fb0e614cf42af1`; config SHA-256 `543261d86f82efef374e9ee50ae02f225d16d759b1407c0d339f9c1725efd7ee`; `LlamaForCausalLMEagle3`, one layer, hidden size `2048`, full vocab `154880`, draft vocab `32000`, BOS `151329`, EOS `151336`.
- Consume `../external_draft_residency_gate/external_draft_identity_gate_2026-07-16.json` as the strict no-translation closure. Do not reopen its candidate search.
- Workload/economics: target-verified, cache-off reasoning-disabled 8,192 input/1,024 output, 32 complete requests, c16, 300 seconds; r3 `552.1710554232396`, ordinary `594.466`, robust `606.355` output tok/s at `$1.10/hour`.
- Residency boundary: `../derived_runtime_mtp_binding/` measured a `1.543-GiB` one-layer MTP addition at `44.22 GiB` in use with `167.38 MiB` free before a failed `562-MiB` allocation during the same c16 geometry.

## Scope and stop rule

Within 1,200 seconds, 10 GiB RSS, 96 MiB new artifacts, and `$0`, audit only this pinned EAGLE3 candidate. Use official repository metadata/card, config, safetensors header or bounded range metadata, and pinned vLLM source. Do not download the full weight payload. Decide in fail-fast order:

1. whether the checkpoint contains an explicit immutable draft-index-to-target-token mapping (or mathematically equivalent runtime contract), and whether target verification operates exclusively in exact target IDs;
2. whether that mapping binds the campaign target's complete tokenizer vocabulary/special-token identity rather than a different GLM revision, and whether the apparent BOS/EOS mismatch is harmless internal metadata or a real target mismatch;
3. whether pinned vLLM `0.15.0` has an unchanged `eagle3` loader/planner path for this candidate architecture, compressed vocabulary, exact AWQ target architecture, and reasoning-off serving semantics;
4. whether exact draft weight bytes plus mapping, draft KV, activations, graphs/workspaces, and fragmentation fit beside target c16 with conservative headroom when reconciled to the native-MTP OOM; and
5. whether candidate-specific acceptance evidence plus a conservative L40S draft/verify-cost bound reaches `606.355` output tok/s. Treat the H200 `54.9%`/`1.66x` report only as a scoped prior unless every relevant identity, workload, and cost component can be bounded.

Do not equate a 32k draft head with a tokenizer. Do not assume a mapping exists because an EAGLE3 runtime supports such mappings generically. Conversely, do not reject a proven exact mapping merely because draft indices differ from target IDs. Require exact hashes/tensor names/source locations and label every claim measured, source-bound, vendor-reported, derived, or inferred.

Return exactly one terminal result:

- `NOMINATE_EAGLE3_L40S_AB`: exact mapping, target identity, pinned runtime, robust residence, and conservative `606.355` path all pass; state one later matched endpoint but do not prepare it;
- `MAPPING_CLOSE`: no explicit exact draft-to-target token bridge exists in the candidate/runtime contract;
- `TARGET_CLOSE`: a bridge exists but binds a different tokenizer or target identity;
- `RUNTIME_CLOSE`: identity passes but the pinned unchanged runtime cannot execute the pair;
- `MEMORY_CLOSE`: execution admission passes but conservative c16 residence fails;
- `ECONOMIC_CLOSE`: a resident executable path has conservative evidence below `606.355`; or
- `UNIDENTIFIABLE`: technical admission survives but current evidence cannot bound L40S endpoint economics.

Do not use CUDA, load or convert full weights, edit shared code, access credentials, mutate a provider, prepare a controller, train, or spend money. Produce one compact JSON and a concise research-log result.

## Available resources

Use the pinned candidate repository, local target/config/tokenizer assets, pinned vLLM source, fixed projects above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
