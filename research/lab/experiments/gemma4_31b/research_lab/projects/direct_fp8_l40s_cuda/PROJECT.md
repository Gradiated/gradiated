# Direct FP8 L40S CUDA falsifier

## Decision and hypothesis

Determine whether the exact pinned checkpoint `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4` can load through current vLLM online FP8 on one Nebius L40S, return correct text, and provide a usable first cost baseline for the campaign workload. The offline bound predicts 40.504 GiB steady residency at 10K and 4.20 GiB headroom. At planning rates, L40S only needs 39.2857% of a valid H100's throughput to win raw GPU cost, but the H100 canary produced no admissible comparator and current vLLM reports make FP8 correctness the first scientific gate.

This project is the exclusive paid provider owner. It consumes `../fp8_l40s_fit_economic_falsifier/FP8_L40S_PACKET.json`; it is not another readiness project and must reach the real CUDA consumer unless a typed pre-create contract terminal fails.

## Immutable experiment contract

- Exact target revision above; text-only, default non-reasoning mode. Capture the tokenizer/model identity and request token IDs.
- Runtime: `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`, amd64 manifest `sha256:8e86cb93b724092cd4dc892fb129a6c5538613b38a5cd34e40aab9e6aea72b03`.
- Placement: one preemptible L40S and one 200 GiB network SSD. The first `gpu-l40s-a` / `1gpu-16vcpu-64gb` create returned 3 before any resource existed. The one director-authorized material correction is the catalog-valid independent pool `gpu-l40s-d` / `1gpu-16vcpu-96gb`; do not retry pool `a`. Use the authenticated actual rate in experiment accounting and `$1.10/GPU-hour` only for production planning.
- vLLM delta: `--quantization fp8 --dtype bfloat16 --enforce-eager --gpu-memory-utilization 0.92 --max-model-len 10000 --max-num-seqs 8 --max-num-batched-tokens 8192 --tensor-parallel-size 1`, with image/audio disabled.
- Reuse the lifecycle and cleanup primitives in the shared Nebius `placement_control.py` / `vllm_smoke_control.py`. Use the shared `vllm_methodology_runner.py` for simultaneous offered load; do not inherit GLM model assumptions or create a second wrapper lineage.

Before provider creation, reuse the passing rendered contract audit and check only the changed placement plus empty inventory. Preserve a bounded sanitized provider diagnostic on any create failure: retain the error class/code/message needed to distinguish capacity, quota, placement, and request errors, while removing credentials, authorization material, cloud-init, project/tenant IDs, and public keys. The complete remote plan must still prove that host, mount, container, and request paths agree; the shared runner produces actual overlapping c1/c8/c16 requests rather than serial loops; primary and 10K arms exist; model/image/sampling identities are bound; prompt/decode/TTFT/ITL/queue/complete-request telemetry and raw outputs are retrieved; and deadline/watchdog/cleanup identities agree. Do not weaken the passing audit.

The pool-d diagnostic subsequently proved that both initial creates shared one deterministic request-construction defect: `build_create_command` passes the generated resource name directly to `--hostname`, while the owner generated uppercase `T`/`Z` timestamp characters. The lowercase correction then created a valid pool-d instance, but its project-local raw `scp` used `StrictHostKeyChecking=yes` without the shared campaign known-hosts path and failed before staging; cleanup passed. That custom-owner lineage is closed. The scientific project remains open for exactly one fallback through the last proven shared transport: use `stock_control.scp_to`, `stock_control.run_ssh`, shared known-host refresh, `VerifiedRetainedOwner`, and the independent watchdog. Do not add or copy another controller wrapper. Reuse the lowercase name, pool d, passing rendered science audit, and all immutable inputs. Any failure of this shared transport path before CUDA closes the project.

## Scientific sequence and gates

1. Start one bounded durable local owner plus an independent provider cleanup watchdog. Checkpoint staging, compilation, and the actual consumer may outlive a model response; leave the correct owner running and record it in `STATUS.json` rather than killing or restarting it for turn cadence.
2. Reach health, then run short deterministic greedy probes. Capture raw text, token IDs, server logs, memory, and errors. Non-empty output alone is insufficient: degenerate repetition, incoherent/gibberish text, scale/kernel errors, timeout, or reload closes FP8 immediately with cleanup and no support successor.
3. If correct, run complete 4,214-input/358-output requests at actual simultaneous c1 and c8. Run c16 only as offered-load/queue evidence after c8 is healthy. Preserve successful-request counts, prompt/decode tokens/s, TTFT, ITL, queue time, utilization, power, memory, failures/reloads, and wall-clock cost.
4. Run the methodology-matched 10K-input/358-output single stream. Keep it separate from aggregate throughput.
5. Report fresh-input, cache-read, and output economics separately. For the starting mix the retail component benchmark is `$0.12/M`, `$0.09/M`, and `$0.35/M` with 12.7% prompt cache reads; do not claim self-hosted cache savings without an actual cache arm. Include utilization/headroom, storage, failures, and orchestration. Because the H100 lineage is inadmissible, report L40S absolute sustainable cost and the future H100 break-even formula, not a fabricated matched speedup.

Broad production quality remains deferred, but no result is production-eligible without later quality and feature validation.

## Pre-registered retained-session follow-up

Checkpoint staging is expected to dominate scored GPU time. The completed saturation bound supersedes the generic async fallback: c4 is conservatively safe, while BF16-KV c8 is 0.342 GiB outside the bound. Prepare exactly one adjacent conditional FP8-KV c8 arm through `../fp8_kv_c8_retained_arm/FP8_KV_ARM.json`. Retain the existing allocation only if stock online-FP8 weights pass raw correctness, c4 completes, c8 is memory-limited or c4 misses the sustainable-cost gate, the FP8-KV packet passes its typed identity/quality/start audit, and it is start-ready within ten minutes. Reuse the same checkpoint/image content and sequential owner/watchdog, restart only the server, and compare deterministic token IDs plus complete c8 requests. If any trigger is false, tear down immediately; do not retain for async scheduling, MTP, prefix cache, or another arm.

## Budgets and terminal contract

- Wall clock: 3 hours for the durable project owner; provider exposure: at most 2 hours.
- Compute: one L40S for at most 2 GPU-hours and at most 3 local CPU-hours.
- Storage: one 200 GiB provider disk and at most 8 GiB of retrieved artifacts.
- Spend: `$6` maximum, including compute and disk; one paid allocation at a time across the campaign.
- Stop on the first of: typed pre-create failure, load OOM/kernel incompatibility, incorrect first outputs, owner deadline, spend cap, or verified completion. Always emit typed scientific/failure, exposure/cost, and cleanup artifacts. Cleanup passes only with zero matching and zero total campaign instances/disks.

`STATUS.json` must name any live systemd owner, PID/cgroup, watchdog, provider resource identities, deadline, artifact root, and expected typed terminal. A rescheduled researcher in this same project reconciles that owner; no support successor owns it.

The active shared-transport owner was launched before a later static review found that its remote command uses `vllm serve "$m"` without explicit `--served-model-name "$m"`, while the probe and load runner request `google/gemma-4-31B-it`. Do not mutate, stop, or restart the live owner. Its terminal is scientific only if the actual server accepts that requested model identity and emits complete raw requests; a 404/model-alias rejection is an operational identity-boundary failure. After verified cleanup, do not repair this project-local runner again; the director must redirect through a fully parameterized shared endpoint controller.
