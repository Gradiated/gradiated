# Research log

No researcher result yet. Execute the matched L40S representation/capacity experiment in this turn; source support or launcher preparation alone is not a result.

## 2026-07-15 — FP8-c32 dispatch blocked before measurement

**Question.** Can `fp8_e4m3fn` KV state admit the fixed 8,192/1,024 c32 current-AWQ workload on one L40S and reach 594.466 output tok/s?

**Action.** Added the narrow shared-launcher contract for `--kv-cache-dtype fp8_e4m3fn` and c32, with a 31-test regression pass, then created one owned L40S allocation. The recovered arm staged the exact FP8-c32 command, but the resident derived runtime image was absent: Docker reported `pull access denied` for the local-only `glm-vllm:0.15.0-transformers-1618d44` tag. One in-place bootstrap correction was attempted on the retained allocation; its controller was interrupted before a durable bootstrap/transfer or GPU workload completed. The owned instance and disk were subsequently observed absent.

**Evidence.** The create path and instance identity are retained in [events.jsonl](artifacts/fp8_kv_c32_l40s_2026-07-15-r1/events.jsonl) and [provider-create-diagnostic.json](artifacts/fp8_kv_c32_l40s_2026-07-15-r1/provider-create-diagnostic.json); the typed missing-image diagnostic is [repair-01-remote.stderr.log](artifacts/fp8_kv_c32_l40s_2026-07-15-r1/repair-01-remote.stderr.log). The recovery record is [events.jsonl](artifacts/fp8_kv_c32_l40s_2026-07-15-r1-recovery/events.jsonl). No server loaded, so there is no representation proof, VRAM, request, semantic, quality, GPU, or cost-proxy result.

**Interpretation and next move.** This is an external-controller/observability blocker, not an FP8 failure and not a capacity result. Re-admit only through a durable controller that completes the derived-image bootstrap on the retained instance; then run the specified stock-c16, FP8-c16, and FP8-c32 arms without treating the historical c16 throughput as a new adjacent control.

## 2026-07-15 — r2 durable serialized run in progress

**Action/evidence.** Launched `fp8-kv-c32-r2.service` as the sole systemd-owned envelope. It created one L40S, completed the digest-pinned vLLM/Transformers preflight, and transferred the content-verified 20.17 GB AWQ checkpoint in 362.884 seconds. The retained stock BF16-KV c16 arm is now running; the service queues FP8 E4M3 c16 and c32 only after its terminal artifact. Artifacts are under `artifacts/fp8_kv_c32_l40s_2026-07-15-r2/`.

**Interpretation.** No FP8 or throughput result exists yet. The r1 bootstrap/recovery race is avoided: there is one live allocation and no concurrent recovery or provider probe.

## 2026-07-15 — r2 terminal server-start/observability failure

**Question.** Could the serialized stock BF16-KV c16 arm establish the required retained control before FP8 c16/c32?

**Action/evidence.** The durable owner completed runtime preflight and verified the 20.17 GB checkpoint transfer, then the stock arm repeatedly refused `127.0.0.1:30000`. Its remote session ended without the required archive, yielding typed `StockError: artifact retrieval failed`. [events.jsonl](artifacts/fp8_kv_c32_l40s_2026-07-15-r2/control-c16/events.jsonl) records the stage sequence and cleanup; [remote.stderr.log](artifacts/fp8_kv_c32_l40s_2026-07-15-r2/control-c16/remote.stderr.log) retains the repeated refusal. The final record is [R2_TERMINAL.json](artifacts/fp8_kv_c32_l40s_2026-07-15-r2/R2_TERMINAL.json): 2,466.438 s and $0.587918 derived at the measured rate, with zero final instances/disks.

**Interpretation and next move.** This closes the route under the final-readmission stop rule. FP8 c16/c32 did not start, so there is no valid representation, capacity, quality, throughput, or $0.514/M evidence; the missing remote archive makes server-specific cause an observability failure, not an FP8 negative. Do not retry this lane.
