# Research log

Opened by the 2026-07-16 director after corrected FP8 KV reached terminal scientific incompatibility on the exact L40S/vLLM/MLA stack. Execute the already source-bound fixed top-2/no-shared MoE proxy as one direct full-model c16 arm. Integration and measurement are one researcher return; do not stop at readiness.

The inherited proxy artifact is `../adaptive_moe_architecture/artifacts/ADAPTIVE_MOE_C16_PROXY_2026-07-15.json`, current SHA-256 `cf821ccfb8457698c41134be571410930758f294d23eab1bb0fa2e42ea75084b`. Treat its `13.288%` ceiling as synthetic nomination evidence only. The measured decision is absolute completion and throughput against `594.466` output tok/s; the r3 `552.171055` c16 result is contextual, not adjacent.

## 2026-07-16 — terminal direct c16 result

Question/action: ran the one candidate-only external-systemd L40S c16 arm after adding the fail-closed `--moe-top2-no-shared` binding to the shared launcher. Focused launcher tests (`35`) and AWQ-control tests (`7`) passed. The arm bound the current AWQ manifest, the source patch `69f340…`, cache-off 8K/1K c16 geometry, and `(16,)` frontier.

Evidence: provider create, SSH, runtime bootstrap, CUDA/Transformers preflight, and immutable checkpoint transfer all passed. The remote archive `artifacts/nebius_l40s_moe_top2_no_shared_c16_2026-07-16-r1/vllm-awq-batch.tar.gz` (SHA-256 `9c2638fbc7322b04361ca23bb07101ccec0a22cff1590e92309209febe234b6b`) preserves patch application hashes for both vLLM GLM files, model identity, GPU telemetry, server command, and server stderr. During model initialization, `glm4_moe.py:222` in the patched path failed under TorchDynamo with `TypeError: can't multiply sequence by non-int of type 'float'` at `fused_moe_out * self.routed_scaling_factor`; the API server never became healthy and no `allocation-result.json` or request rows were produced. Telemetry reached 18,377 MiB device memory, so this is not a provider/bootstrap failure.

Interpretation: `SCIENTIFIC_FAIL` for this fixed top-2/no-shared source implementation—not a throughput sample and not a quality result. The one allowed arm used `1111.682` allocation seconds and `$0.264988625` derived exposure; `summary.json` records zero final instances and disks. No retry is authorized; preserve the archive and move to the campaign’s next independent mechanism.
