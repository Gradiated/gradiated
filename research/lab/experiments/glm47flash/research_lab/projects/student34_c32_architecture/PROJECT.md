# Physical 34-layer c32 student

## Question

Can the already screened 34-layer/thirteen-block physical student be materialized reproducibly as the simplest robust-c32 depth proxy, without adding an MLA-rank change?

## Why it matters

Audit corrected a shared memory-accounting bug: the prior 45,851-MiB peak omitted 4,601.160 MiB of removed AWQ weights. The corrected c32 projection is 41,249.840 MiB, leaving 4,818.160 MiB on the 46,068-MiB L40S rather than only 217 MiB. Its fixed-cost endpoint bound is 711.032 output tok/s / `$0.429735/M`, but neither placement nor throughput is measured. This is a larger semantic change than the 39-layer student, yet it is simpler and faster to falsify than combining depth with an unmaterialized MLA-rank rewrite.

## Relevant evidence

- `../distilled_depth_student_architecture/distilled_depth_student_bound.json` contains the valid layer set, weight/KV removal, tensor manifest, and fixed-cost bound; its c32 peak/headroom fields are invalid and must be corrected locally.
- `../distilled_depth_student_architecture/build_student39_checkpoint.py` and manifests demonstrate deterministic physical layer removal, renumbering, MTP exclusion, and shard rewriting for the same source checkpoint.
- `../depth_mla_capacity_codesign/` establishes that the rank-256 nomination was based on faulty inherited memory accounting and is quarantined.
- The paid 39-layer project owns provider mutation and the shared launcher; this project must not edit either.

## Scope

At `$0`, independently recompute the 34-layer c16/c24/c32 memory and economic bounds with removed AWQ weights applied at every concurrency. Materialize exactly the prior deterministic removal set `[3,7,10,13,16,20,23,26,30,33,36,39,43]` from `/root/.cache/glm47flash-awq-ab31d120`, renumber retained serving layers to `0..33`, set `num_hidden_layers=34`, remove source layer 47/MTP, and update every layer-indexed config and quantization-ignore reference. Preserve tokenizer, embeddings, norm, head, quantization metadata, and required non-layer files.

Write the checkpoint below a content-addressed `/root/.cache/glm47flash-awq-student34-<contract-prefix>` root. Bind source and output config/index/shard hashes, exact keys and bytes, and fail-closed idempotent reuse. Run a genuine pinned-runtime registry/quantization/loader source contract or executable dry load that reports consumed, missing, and unexpected keys; label a no-CUDA stop accurately. Do not call index/header consistency a loader pass.

No provider, CUDA allocation, shared-launcher edit, training, distillation, or broad quality work is authorized. Do not interfere with the paid 39-layer session.

## Artifact contract and portfolio decision

Produce `build_student34_checkpoint.py`, `student34_checkpoint_manifest.json`, `student34_runtime_preflight.json`, `student34_corrected_bound.json`, and `RESEARCH_LOG.md`. Nominate at most one later c32 cost arm only if the content-addressed checkpoint is exact, the pinned loader path is real or the remaining GPU-load question is explicit, corrected conservative c32 headroom remains at least 3 GiB, and the economic path remains at least 594.466 output tok/s. Otherwise close at `$0`. Quality and recovery remain mandatory after, not before, a measured cost pass.

## Director parking decision — Cycle 55

The exact 39-layer student has now measured `674.424`, `661.661`, and `734.557` output tok/s at c16/c24/c32 on L40S, so this more destructive 34-layer fallback no longer earns a paid cost-proxy arm. Preserve the content-addressed checkpoint and corrected 4,818.160-MiB c32 headroom evidence, but do not run it, recover it, or edit the launcher. Reopen only if the 39-layer recovery lineage fails for a mechanism-specific reason that additional physical depth removal can plausibly solve; ordinary quality failure is not such a reason.

## Available resources

- Source AWQ: `/root/.cache/glm47flash-awq-ab31d120`.
- BF16 geometry: `/root/.cache/glm47flash-bf16-33faccf4`.
- Existing depth scripts/artifacts: `../distilled_depth_student_architecture/`.
- Runtime and tools: `/root/workspace/research/lab/experiments/glm47flash/campaign_100` and `/root/workspace/research/factory/tools`.
