# Selective W8 head/shared representation gate

## Question

Can a less lossy official symmetric group-32 W8A16 representation for exactly the full-47 `lm_head` plus 46 shared-expert linears use a native pinned-vLLM SM89 load/dispatch path, save enough BF16 payload to matter at c32, and reduce quantization error relative to the measured W4 representation?

## Why it matters

Selective head+shared W4 is the strongest exact-full-47 representation result at `630.195398` output tok/s, but its frozen development signal failed. Stable stock c32 controls cluster near the `606.355` robust threshold, so a less aggressive representation could retain part of W4's performance/capacity benefit while reducing distortion. This is materially different from repairing W4 scope localization: it asks whether W8 is a better representation point and binds the actual runtime path before any checkpoint or provider spend.

## Scope and evidence

- Use stock checkpoint `/root/.cache/glm47flash-awq-ab31d120` at revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`.
- Select exactly `lm_head.weight` plus layers 1–46 `shared_experts.{gate_proj,up_proj,down_proj}.weight`; layer 0, routed experts, attention, and every other tensor remain out of scope.
- Reuse the official selective-W4 producer/config and measured combined W4 root only as exact geometry, payload, and error comparators.
- Audit the pinned vLLM 0.15.0 constructor, loader, compressed-tensors method, and actual SM89 W8A16 dispatch. A generic scheme name or shape divisibility is not a loader/dispatch pass.
- Compute exact BF16 and proposed W8 payload bytes for all selected tensors. On deterministic bounded slices spanning head, gate, up, and down tensors, compare official W8 dequantization error directly with the existing official W4 representation using identical metrics and seeds.

## Resource budget

This is one `$0` offline gate: at most `1,200` wall-clock seconds, `4` CPU-hours, `16 GiB` peak RSS, and `64 MiB` new artifacts. No checkpoint materialization, full tensor rewrite, CUDA, provider query/mutation, shared launcher/controller, or paid work.

## Decision

Return `W8_REPRESENTATION_NOMINATED` only if the exact 139-tensor universe closes, pinned constructor/loader/SM89 dispatch is source-bound, selected-payload saving is at least `512 MiB` versus BF16, all numerical outputs are finite, and W8 error is strictly lower than W4 on every preregistered tensor class. This nominates at most one later direct endpoint; it is not a throughput, quality, capacity, deployability, or economics claim.

Otherwise return a typed `W8_RUNTIME_CLOSE`, `W8_PAYLOAD_CLOSE`, or `W8_NUMERICAL_CLOSE` and stop. Do not materialize a checkpoint, patch vLLM, open a runtime adapter, or create a successor in this project.

## Available resources

- `/root/workspace/research/factory/tools`
- `/root/workspace/research/sol/experiments/glm47flash/campaign_100`
