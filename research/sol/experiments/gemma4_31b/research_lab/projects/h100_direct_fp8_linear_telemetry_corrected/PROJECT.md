# H100 direct FP8 linear sweep with corrected telemetry liveness

## Decision question

After one valid H100 M8 raw CUTLASS FP8 sentinel was blocked only by coarse utilization sampling, do the complete exact M8/M16/M32/M3679 linear floors falsify or preserve the H100 planning envelope?

This is one material correction, not a repair/restart of the closed owner. It changes only telemetry liveness around the separately scored sentinel; raw consumer, inputs, dual oracle, scored timing, geometry, aggregation, image, and lifecycle remain matched. No further correction is authorized.

## Authoritative inputs and identity

- `../h100_direct_fp8_linear_falsifier/artifacts/RECONCILED_TERMINAL.json` SHA-256 `26cace1bfa370e3b578935e44c16beeb7ec396d707d8b08e3253bd19ba4f6756` proves one valid M8 row, false terminal solely from coarse telemetry, and zero-resource cleanup.
- `../h100_direct_fp8_live_program_audit/AUDIT.json` SHA-256 `005753bbbb5427f282d9bc191ad4031d81e8ab181496aac328c82ab007767a42` permits interpretation of the immutable raw program.
- `../h100_direct_fp8_linear_packet/START_PACKET.json` SHA-256 `f6f467fedd60e56cf1a3718d4bdd12941fe7a52afcc7866786f9f428e835c87c` and all packet scientific bytes are the base.
- `../gemma_l40s_parallel_lm_head_measurement_final/artifacts/gemma-l40s-head-final-20260717t065653z/summary.json` SHA-256 `4f2f5162791b1c5643e9ebe4608e8b7583d5c3713216ec5f75d49748ddf0d15b` supplies only the exact pinned actual-`ParallelLMHead` program/shape prior for a possible same-session H100 arm; no L40S timing transfers.

Execution identity remains `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`, image `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, vLLM `0.19.1.dev6+g6d4a8e6d2`, and `NVIDIA H100 80GB HBM3` capability 9.0. `assert_identity.py` mechanically verifies all inputs and the brief before provider access.

## Exact correction and execution

Use the proven shared controller and one sequential `VerifiedRetainedOwner` under one lowercase user-systemd owner/watchdog. Before create, render and behaviorally audit all corrected program/wrapper/trigger/optional-head/owner/launcher/accounting/cleanup bytes and bind them in one typed pre-create terminal. One preemptible H100 plus one 100-GiB disk; one create; zero repair/restart; no checkpoint.

Primary still scores exactly one sliding-QKV M8 row with the same raw `scaled_fp8_quant` → `cutlass_scaled_mm`, matched BF16, corrected dual oracle, five CUDA/wall samples after two warmups, allocator evidence, and exact runtime/source identity. After scored timings are frozen, execute a separate unscored synchronized candidate liveness loop for 1.5–3.0 seconds while sampling telemetry at <=200 ms. Liveness must report positive finite CUDA work and at least one of: nonzero utilization; or memory-used increase >=256 MiB plus power >=20 W above pre-loop idle. The liveness loop is never included in scored timing or aggregation. This replaces the invalid all-one-second-utilization-only predicate; all other gates remain.

Conditional runs only after atomic primary retrieval and exact sentinel/identity/oracle/timing/liveness pass with at least seven provider minutes left. It executes the packet's exact 24 rows and c8/c16/c32 aggregation unchanged. Compare each linear floor with `0.5479752315195353 s/request`; below ceiling is only survival of a lower bound.

## Adjacent same-session arm

Before create, attempt for at most ten wall minutes to prepare one immutable actual H100 `ParallelLMHead` program from the prior pinned-image consumer: M8/M16/M32, deterministic varied-sign BF16 weights/inputs, output-consuming BF16 oracle, stable CUDA/wall timing, and allocator/telemetry. If it cannot be start-ready and content-bound in ten minutes, omit it and record that disposition before create.

If prepared, run it sequentially on the same retained H100/image only under named trigger `H100_LINEAR_SWEEP_PASS_AND_SETUP_DOMINATES`: the complete 24-row linear sweep passes; bootstrap plus image setup exceeds total scored primary+conditional CUDA time; head bytes are already staged; and at least seven provider minutes remain. Report the H100 head floor separately and combined with H100 linears, without transferring L40S timing. Any false trigger cleans immediately. No other retained arm.

## Budgets and terminal

- Wall clock: 28 minutes.
- Provider exposure: 18 minutes.
- Compute: 0.31 H100 GPU-hours plus 2 local CPU-hours.
- Storage: one 100-GiB provider disk; 1 GiB retained plus 512 MiB temporary local.
- Spend: `$1.20` maximum; one allocation; zero repair/restart.

Stop and clean on any identity/hash/kernel/oracle/scored-timing/liveness/telemetry/shape/trigger/deadline failure. After one sweep and optional triggered head arm, clean immediately. Terminal acceptance requires typed stage artifacts, exact exposure/useful-GPU/cost accounting, watchdog identity, and authenticated zero instances/disks.
