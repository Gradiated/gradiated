# Research log

Delegated 2026-07-15. No analysis has run yet.

## 2026-07-15 — current-source AMD falsifier

**Question.** Can the exact GLM-4.7-Flash compressed-tensors AWQ checkpoint run on one rentable high-memory AMD GPU with a replica geometry that beats both $0.568889/M and the measured L40S c16 $0.445308/M point?

**Action.** Performed a zero-cost screen over three current catalog offers and the current SGLang ROCm quantization/model-support sources. Derived required aggregate throughput at each hourly rate and a deliberately conservative 0.5×-per-replica prior anchored to the measured L40S c16 535.286 tok/s. Replica counts use the measured 44,103 MiB peak residence and do not multiply independent device bandwidth without an explicit one-device geometry.

**Evidence.** [AMD_SCREEN_2026-07-15.json](AMD_SCREEN_2026-07-15.json) is the machine-readable matrix and calculation record. MI300X at $1.99/hr requires 971.680 tok/s for the strict hurdle and 1,241.338 for the L40S frontier; four conservative replicas reach 1,070.572, so it clears only the strict hurdle. MI325X at $1.57/hr requires 766.602 and 979.347 tok/s; five replicas reach 1,338.215 and remain below $0.445308/M at 90% productive utilization with 10% lifecycle overhead in the analytical bound. OCI MI355X requires an 8-GPU node at $68.80/hr and 33,593.75 / 42,916.60 tok/s, so it fails economics even under eight times the control prior.

**Interpretation.** The MI325X result is not a nomination. SGLang's current matrix documents generic `awq` on AMD but only partial `compressed-tensors` support, while `awq_marlin` is CUDA-only; release history's GLM-4.7 Flash support does not establish this exact compressed-tensors checkpoint on ROCm. The campaign's exact checkpoint audit also retains an unresolved compressed KV-B post-load boundary. Current catalog listings are not direct capacity/orderability proof. Therefore the exact-support gate fails closed before any paid load or benchmark.

**Decision / next move.** Close AMD for this GLM-4.7 AWQ campaign. Reopen only if a pinned ROCm image/runtime provides exact checkpoint load plus quality evidence and a directly verified MI325X-class capacity/rate; no exact-load nomination is justified this turn.
