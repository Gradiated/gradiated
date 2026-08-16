# Research log

Opened by the 2026-07-16 director after r3 produced a valid adjacent full-model c16 control and an FP8 operational null caused solely by the rejected `fp8_e4m3fn` token. Execute the corrected `fp8_e4m3` c32 arm; do not return another preflight.

## 2026-07-16 — corrected direct c32 arm launched

**Question.** Does the complete pinned current-AWQ model load and complete the exact c32 background workload on an L40S when its KV cache uses vLLM 0.15.0's accepted `fp8_e4m3` token?

**Action and evidence.** Corrected only the shared smoke/recovery argument choices from `fp8_e4m3fn` to `fp8_e4m3`; the c32 command test now asserts that exact environment value and the recovery test rejects the obsolete token. The focused shared suite passed: 39 tests. The corrected launcher SHA-256 is `1ea632fc88f36ffba357ed12dd4ffe99a26e0fa81a265a33a3be7682df284745`; recovery is `73a40d18cd7bf2764b04aaa6ae9a7a329fe598a1bcb4a943b3518276613fcf63`. Local manifest `e201edca…` and authenticated inventory were checked before create. A first transient-unit invocation mixed incompatible service-type settings and made no provider call; the immediate zero-resource result was corrected before launch. The direct `Type=oneshot` unit `glm47-full-fp8-c32-corrected.service` then created only `computeinstance-e00fz86s6ezzq2pm2g` and its matching boot disk. It has passed SSH readiness and entered pinned runtime bootstrap with the exact c32 / 65,536-batched-token / four-KV-split / cache-off / `fp8_e4m3` command, 3,300-second deadline, and no retention.

**Interpretation and next move.** The candidate-only arm is live; no load, OOM, or performance conclusion is available yet. Its durable launcher/watchdog owns cleanup. Reconcile the terminal summary, archive, and zero inventory; do not start another provider action.

## 2026-07-16 — active-owner snapshot

**Evidence.** One grouped snapshot found `glm47-full-fp8-c32-corrected.service` active in `/system.slice/glm47-full-fp8-c32-corrected.service` with main PID `1251711`, only `computeinstance-e00fz86s6ezzq2pm2g` and its matching boot disk, and the 3,300-second service timeout. The durable event stream advanced from runtime bootstrap to successful CUDA/Transformers preflight and transfer probe, then entered `checkpoint_transfer` at `2026-07-16T01:09:28Z`.

**Interpretation and next move.** This is forward progress, not a scientific endpoint. Preserve the independent owner; reconcile its terminal artifact and verified cleanup on the next turn without polling or creating another provider resource.

## 2026-07-16 — checkpoint-transfer ownership preserved

**Evidence.** The single grouped reconciliation snapshot still finds the direct system unit activating with main PID `1251711` in `/system.slice/glm47-full-fp8-c32-corrected.service`, owning only `computeinstance-e00fz86s6ezzq2pm2g` and `glm47-full-fp8-c32-corrected-boot`. The durable event stream remains at the explicitly entered `checkpoint_transfer` phase after successful pinned bootstrap and CUDA/Transformers preflight.

**Interpretation and next move.** No terminal artifact, model-load result, or cleanup state exists yet. Leave this owner untouched and reconcile exactly once after it terminates.

## 2026-07-16 — scientific-workload ownership preserved

**Evidence.** One grouped snapshot found the same direct system unit and sole L40S/disk still active. Checkpoint transfer completed in `367.422` seconds (`20,193,158,555` scheduled bytes, 14 files, one attempt), and the launcher entered `scientific_workload` at `2026-07-16T01:15:35Z`.

**Interpretation and next move.** The requested corrected-token workload is now executing, but no terminal model-load, request-row, or throughput artifact has yet been retrieved. Do not poll or mutate the active owner; reconcile its final artifact and cleanup after termination.

## 2026-07-16 — terminal scientific classification

**Measured evidence.** The corrected server command contains `--kv-cache-dtype fp8_e4m3`, and model construction reached exact MLA backend selection. It then failed deterministically with `head_size=576`, BF16 compute, FP8-E4M3 KV, and `use_mla=True`: FlashAttention MLA and Triton MLA reject the KV dtype, FlashMLA is Hopper-only, and FlashInfer MLA rejects both the L40S capability and this model's `qk_nope_head_dim=192`. No backend is valid, the model never loaded, and no c32 request or throughput row exists. The archive SHA-256 is `6cc3edb28639f6a014035805532fe2dba7e78ea6112a49769578c2b9b572b757`; summary and event hashes are `f138dc36227b886b422c5ff1b4a118ddb8effac33039969804961a78e766df79` and `aff8220f22c847689b3b54d97600f0c55acc3009fb4e30943ecad7c0f15e1d16`.

**Decision.** Classify `SCIENTIFIC_FAIL`, not `OPERATIONAL_NULL`: the corrected token was accepted and the exact runtime/model/device compatibility question was answered. Derived exposure was `$0.248693024` across `1043.319` allocation-seconds; cleanup passed at zero instances and zero disks. Close this mechanism on L40S/vLLM 0.15.0 and release provider authority.
