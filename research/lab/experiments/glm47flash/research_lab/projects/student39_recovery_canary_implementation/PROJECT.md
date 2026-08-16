# 39-layer recovery canary implementation

## Question

Can the source-bound 39-layer recovery proposal be made genuinely executable and reduced to a cheap, decisive teacher-cache plus LoRA canary before considering its 26-GPU-hour full job?

## Why it matters

`../student39_recovery_distillation/RECOVERY_JOB_SPEC.json` identifies a plausible 11,188,224-parameter rank-16 LoRA surface and sequential teacher/student memory envelopes, but its command invokes nonexistent `run_student39_recovery.py`. The synthetic fixture does not prove the exact model class, PEFT target discovery, real cache serialization, checkpoint resume, or loss code against the pinned GLM implementation. Spending `$55.90` before those paths exist is poor information value.

## Fixed evidence and invariants

- Preserve the exact 39-layer mapping SHA-256 `e501ab11290cd38424fd5ed93f9e9fd55145a7ed98cb6acddcc21b4122accb3a`, removed layers `[5,10,15,20,26,31,36,41]`, tokenizer, no-MTP contract, and eventual symmetric W4A16 group-32 serving format.
- Teacher BF16 revision is `33faccf4c2ba82142214d0d4e16232a4e9ccfe10`; the student must initialize only from mapped retained BF16 tensors.
- Training/evaluation data must exclude all frozen development and holdout material. Do not access or generate the holdout.
- Full-job feasibility, memory, and economic estimates are priors, not measured training evidence.

## Scope

At `$0`, implement the actual recovery and teacher-cache entrypoints named by the job contract, or a smaller clearly named replacement reflected back into a canary spec. Bind exact pinned Transformers/PyTorch/PEFT source support. Use meta-device or other no-CUDA construction to prove the real 39-layer model class, all intended LoRA module names/counts, frozen base parameters, eight teacher/student hidden-bridge hooks, top-64 teacher-logit schema, finite KL plus bridge-MSE loss, deterministic shard hashes, resume-safe adapter checkpoints, and fail-closed source/data identity. Exercise the same code on a tiny synthetic cache through at least two optimizer steps and save/reload/resume; negative tests must reject mapping, token, cache, and checkpoint drift. Do not claim the earlier toy packer proves full AWQ conversion.

Calculate the exact teacher-cache bytes per token and free-disk requirement. Replace the 4M-token full job with one informative canary only: at most 250k clean tokens, sequential teacher capture and LoRA training, held-back non-evaluation cache, intermediate loss/KL checks, no full AWQ conversion, and no frozen development run. Specify one H100/H200 provider-safe command, durable ownership/cleanup contract, GPU-hour/spend/timeout cap, and stop rules. Target no more than 4 GPU-hours / `$8.60` at the shared H100 experimental reference; if a defensible canary cannot fit that bound, close without provider work.

Do not allocate a GPU or provider, download a training corpus, materialize the full 46-GiB student, edit the serving launcher, score the BF16 archive, or authorize the 26-GPU-hour job. This project establishes executable canary readiness only.

## Portfolio decision

Nominate exactly one paid canary only if real source-bound module construction, loss/cache/checkpoint execution, contamination controls, disk/memory bounds, and a <=4-GPU-hour terminal contract all pass. Otherwise close recovery as not yet executable. Even a canary pass only unlocks the bounded paid canary after the BF16 control adjudication passes; it does not authorize the full recovery job.

## Artifact contract

Produce the actual trainer/cache code, focused tests, `STUDENT39_RECOVERY_CANARY_PREFLIGHT.json`, `STUDENT39_RECOVERY_CANARY_SPEC.json` only on pass, and a concise `RESEARCH_LOG.md`.

## Director runtime reactivation — Cycle 57

The zero-cost closure treated missing host packages as an external blocker, but the repository host already has the exact local derived serving image `glm-vllm:0.15.0-transformers-1618d44`, image ID `sha256:4672d4aa966cf5f4d437d9f7fd9fb4d1b662a067455f3db46d2ab6cce3f3f62c`, size 29.6 GB. This is the Transformers 5.3.0.dev0/torch/safetensors stack that loaded the exact GLM model in paid runs. Reactivate at `$0`; do not repeat the host import check.

Build or run one content-addressed local training derivative that changes only the addition of a pinned compatible PEFT/Accelerate layer. Record the base image ID, package versions and hashes, and fail closed on dependency or model-source drift. Inside that container, use the exact configs and meta-device/no-CUDA construction to prove the real `Glm4MoeLiteForCausalLM` 39-layer topology, intended target-module discovery and 11,188,224 trainable-parameter count, frozen base, eight bridge hooks, cache tensor shapes, finite real torch KL/MSE, and adapter checkpoint save/reload/resume. The same recovery entrypoint—not a second toy backend—must drive focused positive and negative tests.

If those contracts pass, emit exactly one <=250k-token, <=4-GPU-hour / `$8.60` canary spec gated by the established BF16 V2 control and its frozen NLL ceilings. Do not allocate, download training data, materialize full weights, or edit the serving launcher in this turn. A container build/import/model/PEFT failure closes the canary; another readiness-only handoff is not admissible.

## Available resources

Use the prior recovery artifacts, exact local checkpoint metadata, pinned runtime sources, shared factory tools, and campaign code. Shared accelerator and price inventories are fresh; do not search prices.

## Director scientific admission — Cycle 58

The Cycle-58 zero-cost closure is invalid: `../bf16_v2_capture_adjudication/BF16_V2_CONTROL_ADJUDICATION.json` establishes the control, and `BF16_V2_NLL_CEILINGS.json` exists with SHA-256 `849e057d0dcb6b4d76c6d11093d3e7ce9a6a7e4915b8a6ca3735957889477eff`. Do not inspect the obsolete V35 status again. The real-meta result is useful but incomplete: the current entrypoint has no materialized teacher forward/cache mode, no real LoRA AdamW training mode, no clean-data manifest, and no scientific canary spec. No-op hooks, random fixture tensors, and meta checkpoints do not satisfy this admission.

Continue this same project through one measured recovery canary; do not create another controller or return another readiness artifact. Add narrow `teacher-cache` and `train-lora` modes to the same `student39_recovery.py`, with source-bound streaming materialization of the exact BF16 39-layer student, eight distinct bridge tensors, top-64 next-token alignment, real materialized forwards, real LoRA optimizer state/save/reload/resume, and deterministic clean-data/cache manifests. Select and stage a deterministic FineWeb-Edu slice before provider creation, record its exact revision and document/token hashes, and reject every frozen development hash plus all holdout material. Start with at most 65,536 total 1,024-token tokens, reserving at least 8,192 tokens for non-evaluation held-back cache. Continue on the retained allocation toward an absolute 131,072-token ceiling only if loss is finite, training loss descends, held-back KL does not regress, and the remaining deadline/spend safely fits.

Use the proven lifecycle at `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, adding only one narrow recovery-canary mode. Inputs are BF16 revision `33faccf4c2ba82142214d0d4e16232a4e9ccfe10`, mapping `e501ab11290cd38424fd5ed93f9e9fd55145a7ed98cb6acddcc21b4122accb3a`, base runtime `glm-vllm:0.15.0-transformers-1618d44@sha256:4672d4aa966cf5f4d437d9f7fd9fb4d1b662a067455f3db46d2ab6cce3f3f62c`, derivative `student39-peft:0.19.1@sha256:4e7d66c0f29301823701f466ca485c5ddde7c6e48fff3eadb900c4bb2cc2f0d3`, and a 250-GiB boot disk. Run sequentially so the 58.155-GiB teacher and 46.307-GiB student never co-reside in GPU memory. Require at least 150 GiB free disk before materialization; cache accounting remains 33,152 bytes/token.

The proven Nebius H100-plus-disk experimental rate is approximately `$3.8743055/hour`, not the older `$2.15/hour` feasibility prior. Therefore the hard provider cap remains `$8.60` but the absolute controller/watchdog deadline is 7,900 seconds including setup, retrieval, and cleanup. The first paid gates are exact source/data identity, 80-GiB memory admission, one real teacher forward, one hash-valid cache shard, and one materialized student optimizer step. Stop on any identity, capacity, cache, nonfinite-loss, checkpoint, deadline, or cleanup failure. A pass requires deterministic cache evidence, real checkpoint resume, and positive held-back non-evaluation KL improvement; it only decides whether a larger recovery job is worth admission. It is not candidate development quality, holdout quality, AWQ conversion, or graduation.

## Director pre-create correction — Cycle 59

The latest researcher turn ended during offline preflight without creating a provider resource. Preserve its useful partial artifacts: entrypoint SHA-256 `c23af74c55a3b39605fa0e32b4cb485a6ea02cefe58c7dab126d1b5714faaca2`, 65,536-token file SHA-256 `dc6e850fb0664c03a6f5673a19ab078740f137c12f43112af597499e7c2f5bbc`, and data-manifest SHA-256 `7fb471bc73244cf434911b5fc5e74ff4be23289d706d412346de272a247d41eb`. The staged split is 57,344 train / 8,192 held back across 84 FineWeb-Edu rows. Reuse it only if a corrected fail-closed restaging reproduces the token hash.

Provider creation is not yet admissible. Correct these exact defects rather than restarting discovery: cache full 1,024-token inputs with 1,023 next-token targets so training does not reslice targets to 1,022; require visible frozen-development inputs and nonzero content bindings; request or otherwise verify the declared dataset revision; bind tokenizer, mapping, source, token-file, and every cache-shard hash; invoke the existing exact BF16 39-layer materializer and reject the AWQ proxy as a training base; enable gradient checkpointing; reproduce cache determinism; restore model, adapter, and optimizer and execute one resumed step; and measure finite/descent plus before/after held-back non-evaluation KL. Add focused negative controls for every identity and shape gate.

Pass one tiny execution-equivalent derivative-container cache/train/resume flow before create, then continue in the same return through the sole durable H100 canary under the unchanged `$8.60` / 7,900-second cap. Do not substitute another readiness document. If the corrected path cannot fit the memory or time envelope, close with that typed result. The former 26-GPU-hour job is not admitted: at the measured `$3.8743055/hour` venue rate it would cost about `$100.73`, not `$55.90`, and requires a positive canary plus a newly stage-gated budget decision.
