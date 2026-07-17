# Distilled depth-student architecture

## Question

Can a physically smaller GLM-4.7 Flash student with a bounded set of complete blocks removed create enough L40S c16 cost margin—or a c32/cheaper-memory placement discontinuity—to justify later distillation, unlike the closed five-block runtime-skip proxy?

## Why it matters

The exact c16 control needs a 9.955% endpoint wall reduction to reach 594.466 output tok/s and `$0.514/M`. The earlier five-block skip removed attention, KV, routing, expert work, and weights but reached only a 10.42% optimistic work ceiling with no margin. The newer late-MoE bypass closed even optimistically at 567.053 tok/s because it retained attention/KV and fixed scheduling. A deeper, physically pruned student attacks all of those costs together and can remove weights and KV allocation rather than merely bypassing runtime work. The campaign permits modest recovery training after a cost mechanism is established, but quality remains mandatory before any deployable claim.

## Relevant evidence

- `../layer_depth_architecture/depth_bound.json` gives exact per-block AWQ weight and MLA/KV accounting; five blocks save 1.728 GiB of weights and 0.703 GiB of c16 KV but have only a 597.529-tok/s optimistic ceiling.
- `../decode_tail_moe_bypass_architecture/decode_tail_moe_bypass_bound.json` proves that removing only late MoE work cannot reach the gate.
- `../sequence_early_exit_architecture/` shows a 35-layer decode path is source-representable, but that dynamic paid route is closed and is not reused here.
- `../../hardware/L40S.md` binds the 48-GB SM89 resource limits; the prior depth screen estimates at least 13 sparse blocks must disappear for c32 on KV accounting alone.

## Scope

At zero provider spend, bind the exact current checkpoint revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, its 47 serving layers, the pinned AWQ/vLLM runtime, and the cache-off c16 8,192-input/1,024-output workload. Treat this as a new physical student architecture, not a production claim and not another attempt to run exit-35. Screen exactly two depth points: a 39-layer student removing eight sparse blocks for endpoint margin, and a 34-layer student removing thirteen sparse blocks for the known c32 capacity boundary. Exclude checkpoint layer 47's MTP payload from serving depth.

Choose deterministic, evenly distributed or checkpoint-similarity-supported removal sets without using unavailable activations as if they were quality evidence. Compute exact retained/removed tensors, W4/BF16 bytes, MLA/KV allocation at c16/c32, active FLOPs, launch count/waves, and L40S placement. Derive an optimistic work ceiling and a separately conservative endpoint bound that preserves fixed head, scheduler, and overlap costs; do not promote from proportional layer count alone. For the 34-layer point, calculate whether c32 admission at measured memory headroom changes dollars per token enough to compensate for the larger semantic change.

Build one source-bound physical-student fixture that emits a renumbered layer/config/tensor manifest, proves no dangling or MTP tensors enter the serving graph, preserves hidden/logit shapes and final norm/head, and fails closed on source or checkpoint drift. It may simulate model-forward calls locally but must not edit the shared launcher, allocate CUDA/provider resources, train, or run broad quality. Report checkpoint-derived similarity only as a weak recovery prior.

## Available resources

- Current AWQ checkpoint: `/root/.cache/glm47flash-awq-ab31d120`.
- BF16 tensor geometry: `/root/.cache/glm47flash-bf16-33faccf4`.
- Current control, traces, and tools: `../nebius_current_awq_c16_direct/`, `/root/workspace/research/sol/experiments/glm47flash/campaign_100`, and `/root/workspace/research/factory/tools`.
- Existing depth and chip evidence: `../layer_depth_architecture/`, `../l40s_model_chip_codesign/`, and `../../hardware/L40S.md`.
- Fresh production prices: `/root/workspace/research/factory/data/gpu_prices.json`.

## Artifact contract

Produce `distilled_depth_student_bound.json`, `source_bound_depth_student_fixture.py`, and `RESEARCH_LOG.md`, with exact source paths/hashes and measured/derived/source-bound/inferred labels.

## Portfolio-changing result

Nominate at most one later L40S cost-ceiling arm only if a physical student has a conservative path to at least 594.466 output tok/s or a c32/cheaper-placement point below `$0.514/M`, plus a source-bound manifest and a non-vacuous checkpoint-derived recovery prior. Otherwise close at `$0`. No result from this project is quality-eligible without later distillation and full evaluation.

## Director materialization continuation — Cycle 52

Accept the 39-layer/eight-block student as the sole depth cost-mechanism lead. Its fixed-cost endpoint bound is 631.312 output tok/s and `$0.484001/M`, above the 594.466-tok/s economic gate. Close the 34-layer/c32 branch: 217 MiB of analytical card headroom is not a robust admission result. Do not train, distill, run quality, allocate CUDA, or mutate a provider in this continuation. Campaign policy permits cost-mechanism discovery before recovery and full quality, so make the already-nominated student executable first.

Materialize one deterministic physical AWQ checkpoint from `/root/.cache/glm47flash-awq-ab31d120` using the proven source-to-student manifest. Remove source layers `[5, 10, 15, 20, 26, 31, 36, 41]`, renumber retained serving layers contiguously from 0 through 38, set `num_hidden_layers` to 39, and exclude source layer 47 plus every MTP-only tensor or configuration reference. Preserve tokenizer assets, embeddings, final norm, LM head, quantization metadata, and all other required non-layer files. Rewrite the safetensors shards and index rather than depending on symlinks. Put the result under a content-addressed path of the form `/root/.cache/glm47flash-awq-student39-<manifest-sha-prefix>` and record source, shard, index, configuration, and whole-manifest hashes.

The build must be reproducible, idempotent, and fail closed on source/config/index/tensor drift. Run an exact pinned-runtime static loader preflight proving model/config registry and quantization selection, complete weight-key consumption, no missing or unexpected tensors, no dangling source layer IDs, and hash agreement. A full CPU model load is unnecessary if the static/source-bound proof is exact. Do not edit the shared launcher or prepare provider orchestration.

Produce `build_student39_checkpoint.py`, `student39_checkpoint_manifest.json`, `student39_runtime_preflight.json`, and append the result to `RESEARCH_LOG.md`. If materialization and loader closure pass, leave exactly one later candidate-only 39-layer L40S c16 cost-ceiling action queued behind the active adaptive-MoE terminal. Only a measured economic pass may authorize distillation and full quality evaluation. If physical materialization or loader closure fails, close this lineage without provider work.

## Director paid measurement — Cycle 53

The physical checkpoint at `/root/.cache/glm47flash-awq-student39-183247870f89` is present, contains no symlinks, and its config, index, four shards totaling about 15.54 GB, 22,815 keys, layer renumbering, and no-MTP contract match `student39_checkpoint_manifest.json` (SHA-256 `62d2bf96af65cecbe010ea0758ad232e5a169494bebed857a99d5991da77254c`). Correct one overclaim before create: the existing preflight proves index/header consistency but hard-codes vLLM registry, quantization-route, and key-consumption `PASS`; it is not exact loader closure. Snapshot the source-shard hashes into the durable contract, verify every current student output hash before reuse, and replace those constants with a real pinned-runtime registry/quantization/loader source check or executable dry-load that reports consumed, missing, and unexpected keys. Do not spend the turn rebuilding already matching shards or return another preflight-only handoff. A locally uncorrectable loader contract closes at `$0`; a pass continues immediately to measurement.

Use the current shared launcher `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py` at SHA-256 `d1c1676d66c572958f757104fcbabcd627392f571b3cd2103fe1a3838b4ee48f`, its `l40s-awq` profile, current remote script SHA-256 `afab442b83cedf22cced6d3fd70e9d855c016fa7251449a545cd54eaf5796dbd`, the exact student root above, the current tokenizer, pinned vLLM 0.15.0/Transformers-derived runtime, cache off, 8,192 input / 1,024 output, and `num_kv_splits=4`. Pass the execution-equivalent no-mutation terminal, then run one external-systemd-owned L40S session. Do not create a project-local controller or add a student-specific runtime patch.

Within the retained server, run candidate c16 first and then c24 if c16 completes and the server remains healthy, using `max_num_seqs=32` and frontier concurrencies `16,24`. The derived student peaks are 38,843.5 MiB at c16 and 43,067.3 MiB at c24, leaving about 3,000.7 MiB at c24 on the 46,068-MiB card; label that as derived until measured. Each arm must finish the exact requests within the 300-second background envelope and retain raw rows, finite-output and compact semantic sanity checks, server/GPU/memory/power telemetry, useful GPU seconds, archive hashes, spend, and verified two-view cleanup. A c24 OOM does not invalidate a complete c16 result.

Pass the economic screen if either complete arm reaches at least `594.466` output tok/s at the `$1.10/L40S-hour` planning rate, or `$0.514/M`; report c16 separately against the content-addressed 535.286-tok/s current control and treat c24 as the campaign-authorized latency-for-cost operating point. This proxy is not quality eligible. Only a measured pass opens recovery/distillation and full quality; a valid miss closes physical depth. One material in-place correction after create is allowed. Maximum all-in exposure is `$1.00` and 3,900 seconds, with artifacts under `artifacts/nebius_l40s_student39_c16_c24_2026-07-15-r1/`. This project is the sole provider-mutation owner.

## Director launcher-contract correction — Cycle 54

The r1 continuation correctly stopped at `$0`: `awq_smoke_control.validate_local_model` and the remote AWQ script hard-code the 20,170,199,928-byte control checkpoint, so they reject the exact 15,544,868,264-byte student before provider create. This is a typed launcher-contract failure, not loader or depth-economics evidence. Explicitly authorize one narrow shared correction in the existing launcher path. Preserve the stock checkpoint's exact behavior and add a content-addressed derived-AWQ contract that accepts only the student manifest SHA-256 `d09c1b7dbd10c91eec8aba98fc3f14878bf8d1784d610499935c3e355ba9e86a`, four shards, 15,544,868,264 weight bytes, config SHA-256 `07b92832975cb7d174660e88127e91b6269605fe0cfb1bd9bfd282056969be54`, index SHA-256 `407b00ffcfa0a69174d4d65473f3fd889ccc9cadb88a75d98393ff2034d8153e`, and the existing per-file checksums. Pass the selected expected bytes and manifest identity to the remote verifier rather than trusting arbitrary manifest values. Tests must prove that stock mode rejects the student, student mode rejects stock or drift, and neither can select H100/BF16. Do not create another controller or a project-local launcher.

At this decision point the shared launcher is SHA-256 `d1c1676d66c572958f757104fcbabcd627392f571b3cd2103fe1a3838b4ee48f` and the current remote script is SHA-256 `afab442b83cedf22cced6d3fd70e9d855c016fa7251449a545cd54eaf5796dbd`; record the post-correction hashes rather than preserving these pre-edit values. The earlier log's remote-hash mismatch is not present in the current filesystem. After focused tests and execution-equivalent no-mutation validation, continue in the same return under external systemd to the paid session. Another readiness-only return or local contract-only closure terminally closes this route.

Correct the inherited c32 memory arithmetic before interpreting placement: the old formula omitted the 2,831.483 MiB of removed AWQ weights at c32. The corrected student39 projections are 44,459.517 MiB at c32 and 1,608.483 MiB of card headroom. Run c16, then c24, then c32 while the retained server is healthy, with `max_num_seqs=32` and frontier concurrencies `16,24,32`; an OOM or invalid later arm does not erase an earlier complete result. The exact workload, 300-second arm envelope, telemetry, absolute 594.466-tok/s economic gate, semantic-proxy label, `$1.00` spend cap, 3,900-second timeout, and cleanup contract are unchanged. Use fresh artifacts under `artifacts/nebius_l40s_student39_c16_c24_c32_2026-07-15-r2/`.
