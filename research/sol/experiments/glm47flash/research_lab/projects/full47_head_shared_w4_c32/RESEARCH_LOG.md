# Research log

Opened from the 2026-07-16 user-directed architecture/kernel pivot. Make research progress through implementation and measurement; keep handoffs concise.

## 2026-07-16 — durable c16/c32 selective-W4 owner launched

Question/action: bound the tile-legal `lm_head` plus 46 layers of shared-expert BF16 tensors to the checkpoint's group-32 W4 contract. The remote binder converts exactly 139 tensors, removes only their compressed-tensors ignore entries, and patches the pinned `CompressedTensorsConfig` to select the existing linear method for `ParallelLMHead`; routed experts, layer 0, MLA, routing, and all depth stay unchanged. It then started one full-47 cache-off L40S AWQ c16/c32 arm under `glm47-head-shared-w4-c16c32-20260716-r1.service` with `RuntimeMaxSec=4500s` and a 600-second background-arm envelope.

Ownership snapshot: PID `1394589`, cgroup `/user.slice/user-0.slice/user@0.service/app.slice/glm47-head-shared-w4-c16c32-20260716-r1.service`, active/running at launch. The resource identity is pending provider create (`glm47-head-shared-w4-c16c32-r1` and its boot disk); the shared launcher installs its independent provider cleanup watchdog immediately after create. Artifact root: `artifacts/full47_head_shared_w4_c16c32_20260716_r1`. This is an active measured owner, not a readiness result; reconcile its terminal archive, request completion, memory, throughput, spend, and cleanup on the deferred turn.

The first durable owner was an observable pre-provider operational null: systemd started it from `/root`, so its relative launcher path was absent (exit 2; no artifact beyond `r1/experiment-spec.sha256`, no provider call). The one material correction used absolute paths. The active replacement is `glm47-head-shared-w4-c16c32-20260716-r2.service`: PID `1394913`, the matching app-slice cgroup, `RuntimeMaxSec=4500s`, deadline epoch `1784189769`, resource identity pending create `glm47-head-shared-w4-c16c32-r2`/`-boot`, and artifact root `artifacts/full47_head_shared_w4_c16c32_20260716_r2`. Its content-bound spec is `d39858ae…`. Do not poll it in this turn; reconcile the durable owner later.

## 2026-07-16 — Director r2 reconciliation and one clean r3 handoff

- r2 is inactive and exited before create when the shared launcher observed transient nonempty instance inventory; its only artifact is the spec hash. Fresh authenticated inventory now contains zero instances and zero disks. This is operational-null evidence, not a selective-W4 result.
- Correct the memory interpretation: exact saving is `1,029.966629 MiB`, projecting c32 to `45,845.733 MiB`, only `222.267 MiB` under visible capacity and not robust memory admission.
- Re-delegate one absolute-path r3 with unchanged scientific identity. No further implementation correction or controller lineage is allowed. Prebuild the shared-W4/BF16-head ablation and retain only on the named `[594.466,606.355)` c32 trigger using verified runtime only.

## 2026-07-16 — Cycle 102 local admission before the sole r3

Fresh audit confirms zero provider inventory and no live owner, but also no materialized combined or ablation checkpoint root: r1/r2 contain only spec hashes. First produce one bounded `$0` admission packet proving the exact 139-to-417 conversion, state/index closure, unrelated tensor byte identity, derived bytes, and both content addresses. Bind the existing sequential owner to evaluate the authenticated c32 result before retention; unconditional keep is forbidden. On admission pass, run the sole absolute-path r3 with the 300-second envelope. The retained log identity correction is r1 `d39858ae…`, r2 `82297704…`; r3 must hash the final spec and manifests anew.

## 2026-07-16 — `$0` payload/closure passes; runtime admission pending

Action/evidence: `materialize_admission.py` produced [`LOCAL_ADMISSION.json`](artifacts/local_admission_r3/LOCAL_ADMISSION.json). The combined root is `/root/.cache/glm47flash-awq-full47-head-shared-w4-1bd3249b9802` (manifest `1bd3249b…`, `19,090,237,368` weight bytes); it removes exactly 139 serving BF16 tensors and adds exactly 417 W4 packed/scale/shape tensors. The ablation root is `/root/.cache/glm47flash-awq-full47-shared-w4-bf16-head-6cd4cde5185c` (manifest `6cd4cde5…`, `19,546,203,552` bytes), with 138-to-414 shared-only closure. For each root, raw safetensors payload hashes match the immutable source for every unrelated tensor (`28,082` and `28,083` respectively).

Correction evidence: the first local materialization predicate included the three layer-47 MTP shared tensors (`142` rather than `139`); it never created provider state. Restricting the scope to serving layers 1–46 produced the passing packet above. The named existing recovery helper was checked: it requires a preselected `--keep-instance-after-result`, so it cannot implement the director's authenticated conditional-retention trigger. Do not create r3 through that helper or use unconditional retention; bind a compliant sequential owner before the one provider create.

## 2026-07-16 — Cycle 103 admit r3 with normal cleanup

Do not spend another turn building a trigger-aware controller. The preregistered ablation is ready, but the existing retained path cannot keep only after the named endpoint trigger; therefore the campaign's fallback is normal cleanup. Launch the sole r3 immediately from manifest `1bd3249b…` under the proven absolute launcher and one owner/watchdog, run c16 then c32 with the 300-second envelope, and tear down. No adjacent arm, retention, repair, or second create is admitted.

## 2026-07-16 — Cycle 103 runtime-admission correction

The deeper source audit overrides the cleanup-only launch handoff before any provider mutation. `LOCAL_ADMISSION.json` proves bytes and state/index closure, but the combined config still targets only `Linear`; prior exact evidence shows scheme lookup fails for the actual `ParallelLMHead`, and no shared-expert load/sum or numerical oracle exists. Permit one final `$0` correction: target only `lm_head`'s `ParallelLMHead` with the existing W4 scheme, prove exact head/shared method selection, state load, no BF16 duplicate/fallback, TP/logits/sampler/shared-sum contracts, and deterministic error/saturation fixtures. In the same bounded change, add named-trigger evaluation to the proven systemd owner so the already-ready ablation uses the existing recovery path only for c32 `[594.466,606.355)`; otherwise clean immediately. Fail before create on either gate.

## 2026-07-16 — exact runtime oracle rejects current root before provider create

Action/evidence: [`RUNTIME_ADMISSION.json`](artifacts/runtime_admission_r3/RUNTIME_ADMISSION.json) tested the pinned vLLM image against combined root `1bd3249b…`. The source dispatch predicate alone is insufficient: `CompressedTensorsConfig.get_quant_method(ParallelLMHead, "lm_head")` remains null both before and after the in-memory predicate edit, while a serving shared-expert Linear resolves to `CompressedTensorsLinearMethod`. The converted head payload is present and its BF16 key absent, as are the shared equivalents. This is the exact missing scheme-target defect: the materialized config contains only `Linear`, so no `ParallelLMHead` target can match. No provider, systemd owner, or GPU was started.

One bounded correction was applied to the root binder: it now adds a `parallel_lm_head_w4` group targeting only `ParallelLMHead`, with the original group-32 W4 scheme. Both roots must be regenerated and re-oracled before r3; launching now would silently reject the head representation.

## 2026-07-16 — IMPLEMENTATION_CLOSE_INVALID_UINT4B8_PAYLOAD_AND_NONEXECUTING_ORACLE

Final format audit closes this lineage before provider spend. The binder packs signed values with `q & 15`, but pinned compressed-tensors stores 4-bit symmetric codes as `q + 8` and Marlin consumes `uint4b8`; every derived nibble is therefore misencoded. The reused oracle dequantized the original `q`, not runtime-formatted packed bytes. Separately, `runtime_admission_oracle.py` edits the module after import, so its dispatch observation never executes the patch. Correcting both payload and native load/oracle behavior exceeds the single-final-correction stop rule. Quarantine roots `1bd3249b…` and `6cd4cde5…`; no r3, retention trigger, or provider mutation occurred, and authenticated inventory is zero.
