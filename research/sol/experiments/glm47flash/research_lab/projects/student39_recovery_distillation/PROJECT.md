# 39-layer student recovery feasibility

## Question

What is the smallest executable post-training or distillation route that can recover the exact measured 39-layer physical student without changing its serving architecture, W4 inference geometry, or cost mechanism?

## Why it matters

The exact student at `/root/.cache/glm47flash-awq-student39-183247870f89` measured `674.424`, `661.661`, and `734.557` output tok/s at c16/c24/c32 on L40S, corresponding to `$0.453062/M`, `$0.461801/M`, and `$0.415973/M` at the campaign's `$1.10/hour` planning rate. All arms clear the `594.466`-tok/s economic gate, but the untrained structural proxy is not quality eligible and its deferred diagnostic truncated `dev_retrieval_01`. Recovery is now the highest-value model question.

## Fixed evidence and invariants

- Teacher BF16 checkpoint: `/root/.cache/glm47flash-bf16-33faccf4`, revision `33faccf4c2ba82142214d0d4e16232a4e9ccfe10`, manifest SHA-256 `515b831798895e737cfee5943cb522db95cf71d48bb15dfb3f49a016cab9e101`.
- Source/current AWQ checkpoint: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`.
- Student contract removes source layers `[5,10,15,20,26,31,36,41]`, retains and renumbers the other serving layers to `0..38`, excludes layer 47/MTP, and is content-addressed by manifest contract SHA-256 `183247870f8965b8b92260b167eb5c22f486210bf86ffb8a8a4bb0226799caf1`.
- Measured cost archive: `../distilled_depth_student_architecture/artifacts/nebius_l40s_student39_c16_c24_c32_2026-07-15-r2-repair02/summary.json`, artifact SHA-256 `f9f3f77da53d30e87604d8a0f8c1ddd81e8bed65bab100896b06b5c6a7b35383`.
- The serving architecture, 39-layer depth, hidden size, MLA ranks, expert geometry/top-k, tokenizer, reasoning-off policy, and compressed-tensors W4A16 group-32 output format are fixed. A recovery proposal that restores removed blocks or changes those shapes loses the measured cost transfer.

## Scope

Use one zero-provider turn to produce executable recovery feasibility rather than a generic training survey. Bind the exact trainable initialization implied by the retained BF16 teacher layers and prove all config/tensor mappings, layer renumbering, final norm/head, tokenizer, and no-MTP invariants. Determine whether the smallest credible route is adapter/LoRA recovery, selective full-weight recovery, hidden-state matching across the removed-layer spans, logits/KL distillation, or a tightly justified combination. Use exact parameter counts, activation/checkpointing geometry, optimizer-state bytes, sequence geometry, teacher/student placement, and current available accelerator classes to calculate memory, GPU-hours, checkpoint conversion, and the minimum data/teacher-output contract.

Prefer an executable meta-device/source-bound training preflight and one-step synthetic fixture over prose. It must exercise loss wiring, frozen/trainable parameter selection, teacher-to-student layer alignment, checkpoint save/reload, and deterministic conversion back to the exact W4 serving contract without allocating a provider or claiming quality. Do not materialize another multi-gigabyte checkpoint unless it is necessary for the chosen preflight and content-addressed/idempotent. Do not train on the frozen development or holdout evaluation cases, access/generate the sealed holdout, edit the serving launcher, run a GPU, or mutate a provider.

Return exactly one bounded future recovery job only if it has a plausible modest-compute path, an identified data source permitted by the repository/campaign, a reproducible training and quantization command contract, intermediate fail-fast metrics, a spend/timeout estimate, and no contamination of the frozen evaluation. Otherwise close recovery feasibility and state the cheapest decisive missing evidence. Do not nominate multiple recipes.

## Decision and quality gates

A future recovery job must preserve the measured architecture and first pass a development gate before any holdout: at least 5/6 point score in every one of the six frozen categories, valid runtime input-logprob artifacts against the BF16 ceilings when available, no truncation/malformed transport result, and deterministic checkpoint identity. The full quality and provider-matched graduation work remains separate. This project may prepare that handoff but must not call a static or synthetic pass recovered quality.

## Artifact contract

Produce `STUDENT39_RECOVERY_FEASIBILITY.json`, `student39_recovery_preflight.py`, `RECOVERY_JOB_SPEC.json` only on nomination, and a concise `RESEARCH_LOG.md`. Label source-bound, measured, derived, inferred, and unmeasured claims explicitly.

## Available resources

Use the exact checkpoints, manifests, quality fixtures, and project artifacts in this lab plus `/root/workspace/research/factory/tools` and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`. Shared GPU prices are fresh; do not perform a general price refresh.

## Director execution-readiness correction — Cycle 56

Accept the source-bound 7,843-tensor mapping, 11,188,224-parameter LoRA surface, and sequential teacher/student memory analysis as feasibility evidence only. Do not admit the 26-GPU-hour / `$55.90` job: its execution contract invokes `run_student39_recovery.py`, which does not exist, and the current synthetic fixture does not prove the exact Transformers/PEFT module selection, real teacher-cache schema, resumable checkpointing, or a provider-safe training command. `student39_recovery_canary_implementation` owns one `$0` correction that must produce and test those exact paths plus a materially smaller canary contract. The full job remains closed unless that project passes and the BF16 archive adjudication establishes a valid control gate.
