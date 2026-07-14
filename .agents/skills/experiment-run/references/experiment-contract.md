# Experiment contract

Before execution, record:

- causal hypothesis and expected direction
- stock control and candidate change
- model/data/workload/software/hardware identities
- quality and correctness gates
- latency, throughput, availability, or SLO target
- maximum spend, wall-clock timeout, and teardown action
- exact command, seed, configuration, and output artifact paths

On failure, preserve the failure log and classify it as invalid, blocked, or falsifying. Do not silently retry a failed placement as if it were an accepted sample. Do not promote a component or synthetic result into a full product claim without a scope-matched end-to-end control.

## Persistent GPU allocation contract

Use this contract when image pulls, checkpoint transfer, compilation, or model load are material relative to the scientific arm.

Before allocation:

- Queue the control, likely diagnostic follow-ups, and conditional intervention arms.
- Give every arm its own hypothesis, changed variable, gates, outputs, and stop rule, even when they share one allocation.
- Separate the session deadline/spend cap from per-arm timeouts and reserve cleanup margin.
- Assign one process as allocation owner and start an independent provider-side or local watchdog that deletes at the absolute deadline.
- Define resident state identities: VM/hardware, driver, image ID, checkpoint manifest, server command, and harness hashes.
- Define which resident inputs are immutable for the session and the exact content-addressed marker used to attest a prior full verification.

During the session:

1. Build and transfer once after cheap preflight passes.
2. Fully hash large immutable inputs once after transfer. Persist an integrity marker containing the expected manifest hash, verified file identities or metadata fingerprint, timestamp, and verifier version. On later arms, accept the marker only while the storage object and metadata fingerprint are unchanged; otherwise perform full verification again.
3. Retrieve and hash each arm before overwriting its output directory. Session-level input verification does not relax arm-level result hashing.
4. Apply observer-only code changes through a mounted input or controlled copy while the server remains live.
5. Restart only the server when dtype, kernels, runtime flags, or model representation change. Recreate compute only when the hardware/driver/image changes or state integrity cannot be established.
6. Preregister an amendment before every in-place repair. Record the parent spec, measured failure, causal change, unchanged controls, source hashes, tests, remaining budget, and artifact contract.
7. Treat top-level and nested typed errors as harness/infrastructure failures until their causal scope is established. Do not equate the presence of a typed result file with a completed scientific result.
8. After every error or completed arm, immediately choose between another materially changed test and teardown. Keep the allocation when the next test can start within ten minutes. Teardown only when preparation exceeds ten minutes, the lineage is scientifically complete, state is unsafe, or a budget/deadline stop fires.
9. Do not rerun an unchanged failed placement or arm.

For trace-selected kernel work, first record the exact tensor shapes, dtypes, hardware limits, stock source hash, correctness oracle, and expected end-to-end contribution. Sweep launch/tile choices in a standalone microbenchmark when possible. A configuration that exceeds registers, shared memory, or another hardware limit is feasibility evidence; a faster component advances only when its prospective end-to-end effect clears the preregistered threshold.

For final teardown:

- Stop servers and telemetry after evidence packaging.
- Retrieve archives and sidecars, validate internal manifests, and record hashes.
- Delete compute and attached managed disks.
- Verify resource GET returns not-found and fresh inventories contain no session resources.
- Reconcile total allocation exposure and allocate cost to arms explicitly; distinguish shared setup cost from steady-state measured economics.

An intermediate retained state is not cleanup success. Mark it explicitly as retained, keep the watchdog active, and name the next owner/action in durable events.
