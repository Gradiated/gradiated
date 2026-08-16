# ParallelLMHead W4 runtime gate

## Question

Can one minimal output-layer implementation bind the already-proven exact group-32 W4 head payload to the stock SM89 Marlin WNA16 kernel while preserving vLLM's `ParallelLMHead`, logits, and sampler contracts, without a custom kernel or changes to any non-head tensor?

## Why this matters

The real `[154880,2048]` BF16 head is 605.0 MiB and carries a retained 14.09% output-projection interval ceiling. `lm_head_w4_bridge` proved a deterministic 170.156-MiB group-32 W4 representation, legal SM89 Marlin geometry, and acceptable internal pack/unpack consistency, but pinned compressed-tensors selection returns no method because `ParallelLMHead` is not `LinearBase`. The later L40S component experiment failed during image bootstrap before CUDA; subsequent successful pinned L40S sessions invalidate that operational blocker, so neither runtime integration nor the `3.407616x` M=16 component gate has been scientifically tested.

This is a narrow output-layer runtime question, not a broad loader or kernel project. The existing stricter `3.407616x` component threshold leaves almost no margin between the ideal `3.5556x` payload ratio and the endpoint requirement, making a fail-fast implementation audit valuable before another GPU dollar.

## Fixed evidence

- Exact checkpoint `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`; isolate only `lm_head.weight` and preserve every other tensor and model dimension.
- Exact real-head representation and oracle: `../lm_head_w4_bridge/lm_head_w4_bridge.json` and `../lm_head_w4_bridge/source_bound_head_pack_fixture.py`; packed I32 `[154880,256]`, BF16 scales `[154880,64]`, I64 shape `[154880,2048]`.
- Operational-null component attempt and reproducible packer: `../lm_head_w4_l40s_microbench/`. Its zero-CUDA result is not kernel evidence.
- Pinned runtime is vLLM `0.15.0` with the stock `gptq_marlin_repack`/`apply_gptq_marlin_linear` path and SM89 shape support. Audit current project-local source only; do not broaden to a runtime survey.
- Current full-model r3 c16 is `552.171055` tok/s; robust nomination remains `606.355`. Retain the stricter preregistered M16 component threshold `3.407616x` rather than weakening it from the newer denominator.

## Execution contract

Work offline at `$0` for at most 900 seconds, 8 GiB peak RSS, and 32 MiB of new repository artifacts. Implement or falsify at most one minimal project-local adapter that presents the exact packed head to the existing stock Marlin WNA16 operation while preserving tensor-parallel vocabulary partitioning, logits shape/dtype/device, bias behavior, sampler contract, and the unquantized embedding path. Reuse the existing streaming pack/oracle; do not retain another large payload.

Prove source hashes, exact target selection, load/state-dict behavior, deterministic pack/repack, partition and gather behavior, and numerical agreement with the existing dequantized-W4 oracle on bounded M=`1,8,16` fixtures. The implementation must use an existing compiled kernel and require only a narrow output-layer binding. A custom CUDA/Triton kernel, broad compressed-tensors rewrite, non-head conversion, vocabulary remap, sampler change, or silent key drop closes the project.

Return exactly one terminal result:

- `NOMINATE_HEAD_COMPONENT`: one minimal adapter is source-bound, loadable, contract-preserving, and directly runnable by the existing exact-shape component harness; preregister the later L40S decision as M16 p50 speedup `>=3.407616x` with valid outputs before any full-model c16 arm; or
- `HEAD_RUNTIME_CLOSE`: no such implementation survives loader, partition, correctness, existing-kernel, or bounded-complexity gates.

Do not use CUDA, provider/network resources, mutate the cached checkpoint or shared launcher/runtime, run a full server, prepare a provider controller, train, or evaluate broad quality. A nomination is only permission for a later director to consider the already-bounded component measurement; it is not an endpoint or quality claim. No successor.

## Available resources

Use the fixed projects above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
