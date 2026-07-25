# Research log

## 2026-07-25 — exact-shape output-channel-wide schedule

**Question.** Can the production Gemma 4 31B dynamic-FP8 MLP stream wider
contiguous output-channel regions per CUTLASS scheduler tile at exact M32 and
M384 without changing any consumer semantics?

**Action.** Bound `Gemma4MLP = Gemma3MLP`, `Fp8LinearMethod.apply`,
`apply_fp8_linear`, and the pinned SM90 dispatch by hash. Reused only
scope-matched stock evidence: the exact-width M32 full-chain timing and the
real-weight M384 gate/up and down timings. Implemented an M32
`Shape<128,32,256>, Cluster<1,1,1>, swap_ab` schedule and an M384
`Shape<128,256,128>, Cluster<2,1,1>` schedule. Both retain the stock K tile,
schedule family, scale epilogue, and M multicast. Added a deterministic
full-consumer runner and compiled the extension for SM90 in the pinned image
without a GPU.

**Evidence.**

- Measured: stock exact M32 full MLP median is 125.488 us. Stock exact M384
  gate/up and down medians are 230.640 us and 149.616 us.
- Analytical: modeled M32 intensity is 62.06 FLOP/byte and M384 is 324.03
  FLOP/byte, both below H200's 412.29 FP8 FLOP/byte ridge. The M32 FP8 weights
  are 346.8 MB versus 50 MiB L2.
- Derived: widening only N halves scheduled CTA work tiles at both shapes.
  Dominant weight bytes and the five-kernel MLP launch structure do not change.
- Build-measured: both kernels compile. Dynamic shared storage is 205,824
  bytes at M32 and 214,528 bytes at M384, below H200's 232,448-byte block
  limit. The immutable module SHA-256 is
  `4664d3a6c0ff32bb845bd4d766a549398ecd653191ad1f2f7bfb3da77233b43c`.
- Derived: the measured M384 projections alone occupy at least 1.7107% of the
  qualified c32 batch service window. Each measured M384 microsecond saved
  maps to at least 0.004499 whole-request percentage points before counting
  M32 decode.
- Invalid attempt: the first offline compile used an invalid C++ alias for a
  class-template argument. No CUDA invocation or scientific sample began. The
  alias was corrected and only compilation was retried.

**Interpretation.** The source realization is buildable and physically
distinct from the rejected static-scale, width-16,384, and cluster-orientation
arms. It has a positive service-time mapping but no measured candidate timing.
The causal test is sharp: scheduler tiles must halve while DRAM bytes remain
approximately unchanged; full-chain time must improve at both M32 and M384
with bitwise consumer equality.

**Next.** Stop at `source_complete_candidate`. After the current owner releases
the H200, one director-authorized component-only run may consume the immutable
module with `exact_shape_runner.py`. Admit the result only if every persisted
boundary is finite and bitwise equal and the paired-bootstrap 95% lower bound
on saved time is positive at both row geometries. This project does not
authorize an endpoint.

## 2026-07-25 — execution preparation amendment

**Question.** Does the admitted exact-consumer runner emit every required
component evidence field before the queued H200 comparison?

**Action.** Revalidated the immutable module, source terminal, physical model,
and runner hashes without CUDA. The runner already executed the bound consumer
and alternating CUDA-event comparison, but its persisted result omitted the
raw timing rows and CUDA-graph capture/replay behavior. Added only those output
contracts: per-arm raw event rows, graph capture/replay success, output shape,
dtype, checksum, and finite count. Rebound the runner SHA in
`DIRECTOR_EXACT_CONSUMER_H200_BINDING.json`; module bytes and the scientific
question are unchanged.

**Evidence.** Measured (offline): Python compilation and CLI parse pass for
`exact_shape_runner.py`; immutable module SHA remains
`4664d3a6c0ff32bb845bd4d766a549398ecd653191ad1f2f7bfb3da77233b43c`.
The newly bound runner SHA is
`f206a108c76e019b2a75915785bd79271b661221a0b8f17d8cfc1343586ae837`.

**Interpretation.** This is a repairable evidence-contract omission, not a
scientific result and not a CUDA invocation. The queue boundary remains live:
priority-8560 phase-selective currently owns the retained H200 and
priority-8540 certified-lazy runs next.

**Next.** Do not claim or poll. When both predecessors have released or
terminalized and sufficient lifecycle remains, atomically claim the retained
H200 and run exactly one M32/M384 stock/candidate component comparison.

## 2026-07-25 — queue observation

**Evidence.** Measured from the named predecessor's current `STATUS.json` at
22:16:52Z: `gemma4_certified_lazy_vocab_head` is active, has no terminal, and
records an H200 session on `h200-dflash-adapter-e00vyqp7gxsr34wrtz`.

**Disposition.** The immutable component has not been invoked and remains at
$0.00 project exposure. The exact binding requires that predecessor to release
or terminalize first, so this project does not claim or poll the warm bench.

## 2026-07-25 — reactivation claim race

**Action.** After the director reactivated this project, validated the bound
runner's isolated `--rows 32`/`--rows 384` interface and launched a PID-backed
outer owner. Its atomic claim was rejected before remote staging, Docker, or
CUDA.

**Evidence.** `CLAIM_ATTEMPT_20260725T222527Z.json` preserves the pool stdout
and stderr. The live inventory shows that
`gemma4_certified_lazy_vocab_head` re-claimed the same bench at
22:25:09.553202Z, before the FP8 owner's 22:25:27Z claim. No candidate CUDA
marker exists; project provider exposure remains $0.00.

**Disposition.** Typed pool-availability boundary, not a scientific result.
The owner implementation and immutable local packet remain ready for the
unchanged one-shot comparison. Await director re-admission rather than replay
or substituting another bench.

## 2026-07-25 — certified-lazy launch boundary

**Action.** Per the re-admitted schedule, re-read the H200 pool record exactly
once at launch and returned without polling.

**Evidence.** The retained `h200-dflash-adapter-e00vyqp7gxsr34wrtz` was still
`claimed` by `gemma4_certified_lazy_vocab_head` (its non-stale claim began at
`2026-07-25T22:25:09.553202Z`).
`CLAIM_BOUNDARY_CERTIFIED_LAZY_20260725T2225Z.json` preserves the typed
availability boundary. No FP8 claim, staging, CUDA, candidate invocation, or
scientific sample occurred; conservative project exposure remains $0.00.

**Next.** A subsequent admitted execution turn may perform one fresh read and
claim only if certified-lazy has released the bench ready; it must not poll.

## 2026-07-25 — sole-successor claim boundary

**Action.** Per the 22:30Z director admission, performed the one allowed
launch inventory read for FP8's sole-successor slot and did not poll or claim.

**Evidence.** The current pool record remained `claimed` and non-stale for
`gemma4_certified_lazy_vocab_head`, with heartbeat
`2026-07-25T22:30:57.591995Z` and lease ending
`2026-07-25T23:30:57.591995Z`.
`CLAIM_BOUNDARY_CERTIFIED_LAZY_20260725T223057Z.json` records the boundary.
The local summary formatter had a container-shape parse error after the raw
read; this observer defect did not perform another inventory access or touch
the bench.

**Interpretation.** This is a typed pool-availability boundary, not an FP8
measurement. No claim, staging, CUDA invocation, or scientific sample
occurred; project exposure remains $0.00.

**Next.** Return without polling. On a later admitted execution turn, repeat
one fresh read and atomically claim only if certified-lazy has released ready.

## 2026-07-25 — exact H200 component incompatibility

**Action.** Claimed the director-retained H200 once at 22:41:45Z and staged
the project-local immutable packet. The first remote invocation stopped at a
Docker-socket permission boundary; its diagnostics were preserved and the
repair handshake retained the claim. The authorized privileged retry then
reached the M32 stock/candidate comparator.

**Measured evidence.** `M32_REPAIR.stderr` records nonfinite-free but
non-bitwise-equal outputs at every persisted stage, including final BF16
(`max_absolute_error=0.01092529296875`, `relative_l2=1.0`). Raw stdout,
stderr, exit code, and staging manifest are content-addressed in
`artifacts/h200-component-20260725t224241z/`. Conservative project exposure
is `$0.11543988757775839`.

**Decision.** This is a decision-bearing exactness incompatibility for the
bound immutable module, not a latency sample. Passing requires exact M32 and
M384 results, so M384 and endpoint replay are prohibited. The static FP8
weight-stream realization is closed; no rebuild or substitution is authorized.

## 2026-07-25 — M32 exactness failure localized offline

**Question.** What is the first source/execution boundary explaining the
consumed M32 exact-consumer failure?

**Action.** Verified every hash in
`DIRECTOR_M32_EXACTNESS_LOCALIZATION.json`, inspected the original build
record, ELF fatbinary markers, kernel wrapper, and immutable M32 stdout/stderr.
No bench was claimed and the consumed module was not rebuilt or replayed.

**Measured evidence.** `CANDIDATE_BUILD.json` reports only `sm_90` code for a
module containing architecture-conditional `SM904GMMA` instantiations. The
consumed invocation emitted the exact “without targeting sm90a” device guard
28,478 times. The guard precedes MMA, the scaled epilogue, and output commit;
the wrapper allocates with `torch::empty` and has no explicit post-launch
commit/status check. The comparator consequently observed gate/up relative L2
`1.0` and final BF16 maximum absolute error `0.01092529296875`.

**Interpretation.** The first source defect is the builder's
`compute_90/sm_90` target; the first execution defect is the architecture
guard abort before GMMA issue. Missing output commit is a downstream
consequence. ABI/scale-layout mismatch and legitimate accumulation reorder are
not the first boundary, and this static-module failure does not reject the
weight-stream mechanism.

**Result.** Persisted
`FP8_WEIGHT_STREAM_M32_EXACTNESS_LOCALIZATION.json` with result
`implementation_defect_localized_with_source_discriminator`. Corrected the
source target to `compute_90a/sm_90a`, added a fatbinary target guard, and
added a one-call M32 gate/up discriminator. The corrected source was
syntax-checked only; it was neither built nor run on a GPU.

**Next.** Director disposition only. Keep the consumed module closed and M384
prohibited. Any future corrected build/consumer invocation requires a new
content-addressed module and explicit re-admission.
