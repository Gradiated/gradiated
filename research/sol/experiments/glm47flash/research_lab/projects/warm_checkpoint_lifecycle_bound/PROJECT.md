# Warm-checkpoint lifecycle bound

## Question

Can a persistent checkpoint disk, snapshot, image, or other provider-supported warm-start topology reduce GLM-4.7-Flash AWQ setup and recovery overhead enough for the measured L40S c16 point to remain below the strict provider hurdle at realistic productive utilization?

## Why it matters

The measured c16 science point is $0.445308/M output at 535.286 tok/s, but the strict variant-mismatched provider hurdle is $0.568889/M and requires at least 78.3% productive utilization before lifecycle overhead. The successful current-AWQ session exposed 1,412.452 provider-active seconds for a 61.216-second c16 arm, and the live BF16 transfer independently shows that staging checkpoint bytes can consume tens of minutes. Sustainable cost therefore depends as much on reload, preemption, storage, and queue amortization as on steady-state throughput.

## Relevant evidence

- `nebius_current_awq_c16_direct` events, setup phases, transfer logs, provider exposure, disk cost, and terminal cleanup.
- `artificial_analysis_sustainable_comparator/COMPARATOR_ECONOMICS_2026-07-15.json`, including the 78.3% no-overhead strict-hurdle utilization requirement and 84-batch session bound.
- Current AWQ revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, approximately 20.2 GB; V35's complete BF16 checkpoint is 62.44 GB and provides an independent transfer-rate observation only.
- Existing campaign provider tools, durable-control evidence, and current disk/snapshot/image catalogs.

## Scope

Run one zero-provider lifecycle falsifier. Reconstruct content-bound setup timelines for the successful current-AWQ L40S session and at least one independent retained transfer, separating allocation, SSH/cloud-init, image/bootstrap, checkpoint transfer, integrity verification, model load/compile, warmup, science, retrieval, and cleanup. Use measured timestamps where available and label interval-censored phases explicitly.

Evaluate only provider-supported storage/startup mechanisms that can preserve the immutable AWQ bytes safely: persistent managed disk, snapshot/clone, custom image, regional object/cache staging, or a retained warm allocation. For each viable mechanism, bind current rates, minimum billing, attach/clone/restore semantics, regional constraints, integrity verification, preemption behavior, cleanup, and the production-versus-benchmark boundary. Calculate all-in $/M output over queue fill, batches per session, duty cycle, idle retention, reload frequency, interruption, retry, disk/image storage, IPv4/egress, and orchestration sensitivity.

Nominate at most one later lifecycle canary only if it has a current executable provider path and either reduces measured setup/recovery cost by at least 5% or expands the conservative region below $0.568889/M materially without changing checkpoint, runtime, workload, or quality. State the exact reusable artifact, lifecycle operations, spend/timeout, integrity checks, and deletion contract. Otherwise close warm-start topology and report the minimum session length/utilization needed with ephemeral staging.

Do not create or retain a provider resource, build another general controller, change model science, infer throughput from transfer speed, or claim provider-equivalent quality. Budget is $0 and provider mutation is prohibited.

## Available resources

Use `campaign_100`, the c16 and comparator projects, V35 read-only transfer evidence, provider documentation/catalogs, and shared factory economic tools. Produce a machine-readable lifecycle model, reproducible calculator, and concise research-log decision.

## Portfolio-changing result

A bound warm-start mechanism can earn one later canary after the current quality owner releases provider mutation. A negative result makes long-lived queue amortization an explicit production requirement and shifts further cost work back to hardware, representation, or engine changes.
