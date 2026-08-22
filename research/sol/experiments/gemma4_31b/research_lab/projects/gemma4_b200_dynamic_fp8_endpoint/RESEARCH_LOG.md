# Research log

## 2026-07-28T15:04:24Z — preclaim snapshot gate failed closed

Question: may the admitted dynamic-FP8 owner be launched after the local
snapshot materializer?

Action: took the single required detached-owner snapshot and read
`DIRECTOR_B200_DYNAMIC_FP8_RUNNABLE_OWNER_20260728T1502Z.json` once after it
reported `live: false`. Inspected the named snapshot artifact and the current
retained B200 pool record.

Evidence: `model-verification.log` records all eight required files as `OK`,
but the binding-required
`artifacts/snapshot-materialization-20260728t1451z/SNAPSHOT_TERMINAL.json`
does not exist. The recorded owner is exactly PID `3242485`, start ticks
`136660289`; it has exited. The B200 is still available and unclaimed.

Interpretation: this is a typed preclaim finalization/observability defect,
not a scientific result. The binding requires that exact owner to exit with a
valid terminal and expressly forbids its restart, retry, rehash, replacement,
or interruption. Therefore no owner/driver bytes were implemented or
hash-bound, no B200 claim was made, and no provider exposure was added.

Next move: require a director-issued, scope-preserving disposition for the
missing terminal before claiming the retained bench.

## 2026-07-28T15:17:41Z — adopted snapshot and retained same-claim repair

Action: adopted the director-authorized snapshot terminal using the bound
verification-log and manifest digests plus shard stat sizes only; no
checkpoint bytes were touched. Claimed the retained B200 at 15:10:30Z and
launched the bound controller.

Evidence: three invalid pre-science launcher attempts were retained under the
continuous claim. The first expanded an unassigned Bash local; the next two
remote server logs showed the image entrypoint received `vllm serve` twice,
then rejected `--disable-log-requests`. No `INVOCATION_STATE.json`, server
readiness, CUDA marker, or request result was present. Repair2 has corrected
only those launcher boundaries and reached `endpoint_execution` at 15:17:41Z.

Interpretation: no scientific sample has been consumed. Repair2 owner
`3260799/136787441` remains the durable controller through the unchanged
BF16-control, FP8-consumption-probe, and conditional dynamic-FP8 c32 arms.

## 2026-07-28T15:30:00Z — measured endpoint pair, scoped negative

Measured: BF16 control completed all 32 c32 requests in 23.495297 seconds
(`0.734228 s/request`). Runtime dynamic FP8 selected
`CutlassFP8ScaledMMLinearKernel`; its c1 probe completed, then its one c32
candidate completed all 32 requests in 20.287859 seconds
(`0.633996 s/request`). This is a 13.65% endpoint reduction versus the
contemporaneous BF16 control.

Decision: dynamic FP8 misses the fixed `0.625149 s/request` denominator by
1.42% and the `0.500119 s/request` price-normalized target by 26.77%, so it
is a scoped negative despite the real FP8 consumption and endpoint gain.
Compact retrieved evidence and hashes are in
`artifacts/b200-dynamic-fp8-repair2-20260728t1517z/final-retrieval/handoff/`;
the final terminal is `FINAL_TERMINAL.json` (`2873d1b8…ae86`). Assigned
conservative retained exposure is `$2.49`. The claim was released to
maintenance while preserving the healthy FP8 server on port 30001.
