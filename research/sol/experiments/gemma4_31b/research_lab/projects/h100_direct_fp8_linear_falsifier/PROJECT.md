# H100 direct exact-shape FP8-linear falsifier

## Decision question

Do actual raw CUTLASS FP8 linears on H100, at Gemma 4 31B's exact fused-linear shapes and background concurrency, alone exceed the H100 planning service ceiling or preserve enough component headroom to keep the hardware/representation combination alive?

This is a checkpoint-free deterministic component proxy. It cannot establish endpoint throughput, quality, fit, reliability, or FP8 admission. Only an above-ceiling linear floor falsifies; below-ceiling preserves a lower bound because head, attention/KV, cache writing, quantization, and service overhead are omitted.

## Immutable packet and identity

Consume `../h100_direct_fp8_linear_packet/` without rewriting scientific bytes:

- `START_PACKET.json` SHA-256 `f6f467fedd60e56cf1a3718d4bdd12941fe7a52afcc7866786f9f428e835c87c`.
- `BEHAVIORAL_AUDIT.json` SHA-256 `2c4de127d7596a323df4f38ce95843d245e2c3c6dcbc9232fe9958abd8d0f6a6`.
- `STAGED_MANIFEST.json` SHA-256 `8a35a2574c58a541ba650e28e253d5ad952f2c4eb69f8bd06678d782f3ce3151`.
- `h100_direct_fp8_kernel.py` SHA-256 `5b949a02bbc5eed86637103ee9f07dcad1bda2feb784f92629ef30977172ca5c`.
- `remote_stage.sh` SHA-256 `81f0fd9c1077a97e03795be178b78cee4ca8ab46d9ce6dd20a1b6947b6bee41f`.
- `SOURCE_MANIFEST.json` SHA-256 `e6a1e2752c38dc53a1859d7945a7d7573fa276a3ccab7eb6b72889cdae5e29ea`.
- `h100_contract.py` SHA-256 `4966dbbd51d46969e71ea20983fd8023267b3bc953bbbf6467a276280ed7bfbd`.

Execution identity: geometry `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`; image `docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79`; vLLM `0.19.1.dev6+g6d4a8e6d2`; GPU `NVIDIA H100 80GB HBM3`, compute capability 9.0. `assert_identity.py` must mechanically recompute the packet and brief match before any provider access.

## Execution contract

Use the proven shared `mla_microbench_control.py` plus one sequential `placement_control.VerifiedRetainedOwner` under one lowercase user-systemd durable owner/watchdog. Copy or wrap only lifecycle paths inside this project; packet program/wrapper/contract/source-manifest bytes remain unchanged and are included in the final transitive pre-create terminal. One preemptible `gpu-h100-sxm / 1gpu-16vcpu-200gb` plus one 100-GiB disk; one create; zero repair/restart; no checkpoint or retained follow-up.

Before create require the director assertion, packet audit, exact packet/lifecycle/owner/launcher bytes, authenticated empty inventory, credentials, H100 request, deadline, writable artifact root, accounting, and cleanup in one typed behavioral terminal. Launch immediately on pass.

Primary runs only the separately retrieved sliding-QKV M8 sentinel: installed raw `scaled_fp8_quant` plus `cutlass_scaled_mm`, matched BF16, corrected dual kernel/representation oracle, positive stable CUDA and synchronized-wall distributions, allocator evidence, and H100 telemetry. Conditional runs only when the retrieved terminal has exact identity/type/sentinel pass and at least 420 seconds remain. It executes exactly 24 rows: all six exact shapes at M8/M16/M32/M3679, matched BF16/FP8 with the same oracle/timing acceptance. Aggregate c8/c16/c32 by layer multiplicity; multiply decode by 358 and divide decode exactly once by concurrency; include M3679 prefill once without concurrency division. Compare each linear floor with `0.5479752315195353 s/request`.

## Budgets and terminal

- Wall clock: 25 minutes.
- Provider exposure: 20 minutes.
- Compute: 0.34 H100 GPU-hours plus 2 local CPU-hours.
- Storage: one 100-GiB provider disk; 768 MiB retained plus 384 MiB temporary local.
- Spend: `$1.30` maximum; one allocation; zero repair/restart.

Stop and clean on any identity/source/hash/kernel/oracle/timing/telemetry/shape/trigger/deadline failure. After one valid sweep clean immediately. Terminal acceptance requires atomically retrieved typed artifacts, exposure/useful-GPU/cost accounting, watchdog identity, and authenticated zero instances/disks.
