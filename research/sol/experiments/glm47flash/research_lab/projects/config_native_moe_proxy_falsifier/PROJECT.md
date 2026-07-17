# Config-native MoE proxy falsifier

## Question

Can the exact top-2/no-shared architecture-cost proxy be represented by stock pinned/current GLM runtime configuration and checkpoint structure, without the closed custom-forward patch, and does that native path retain a conservative route to `594.466` output tok/s?

## Why this matters

The combined top-2/no-shared proxy has a synthetic `13.288%` trace ceiling (`617.315` tok/s on the older c16 denominator), while each change alone is sub-gate. Its paid arm failed after GPU initialization because the source-patched forward raised a TorchDynamo type error before server health. That closes the fixed patch, not necessarily a stock config/checkpoint-native expression. A bounded local falsifier can decide whether a genuinely different implementation exists without spending or repairing the failed lineage.

## Fixed evidence

- Consume `../adaptive_moe_architecture/artifacts/ADAPTIVE_MOE_C16_PROXY_2026-07-15.json` and `../full_model_moe_top2_no_shared_c16_direct/` terminal artifacts; do not repeat their trace analysis or repair `moe_top2_no_shared_patch.py`.
- Exact checkpoint revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, manifest SHA-256 `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`, 47 serving layers, 46 MoE layers, 64 routed experts, top-4 plus one shared expert.
- Current full-model c16 context is `552.171055` tok/s; the authoritative L40S gate is `594.466` tok/s at `$1.10/hour` and `$0.514/M`.

## Scope and stop rule

Within 1,200 seconds, 12 GiB RSS, 64 MiB new artifacts, and `$0`, inspect the exact stock pinned runtime and at most one current published stable runtime. Exercise real config/model construction and loader key selection with meta tensors or a minimal synthetic fixture as needed. Determine whether ordinary model configuration can set routed top-k to two and omit the shared expert contribution and weights without source edits, monkey patches, custom forward code, silent unexpected-key drops, or altered attention/KV behavior.

If and only if the native constructor/loader path exists, bind the smallest deterministic derived config/index/key-set contract without copying full weight payloads. Re-evaluate the endpoint admission using the existing proxy plus measured same-stack transfer evidence; summed kernel time alone is not a wall-time coefficient. Return exactly one terminal result:

- `NOMINATE_NATIVE_PROXY`: stock config/checkpoint semantics express the intervention, exact construction/load-set controls pass, and a conservative endpoint bound clears `594.466`;
- `RUNTIME_CLOSE`: stock semantics cannot express top-2 and no-shared without a runtime/source patch or silent fallback;
- `ECONOMIC_CLOSE`: the native path exists but conservative endpoint transfer misses the gate.

Do not mutate a provider, use CUDA, materialize full checkpoint weights, edit shared launchers/runtimes, repair the prior patch, train, evaluate quality, or open a successor. A nomination permits a later fresh GPU project only after exit-35 cleanup; it is architecture-cost evidence, not a quality-preserving model.

## Artifact contract

Produce one compact JSON binding runtime/source/config identities, constructor and loader controls, derived key-set identity if applicable, endpoint bound, and terminal decision. Append a concise `RESEARCH_LOG.md`; keep any probe project-local.
