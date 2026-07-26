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

## 2026-07-26T04:41Z — reactivated SM90a include-build execution

**Decision and scope.** The director re-admitted the retained warm H200 for
exactly one fresh `sm_90a` module and one unchanged M32 gate. The prior
failure was pre-CUDA. This execution changes only the pinned CUTLASS include
root: it uses the complete in-image TileLang CUTLASS tree with the pinned
SGLang dispatcher after the already-bound redundant-header removal. Tile,
cluster, scales, ABI, output dtype, workload, and comparator are unchanged.

**Execution.** Claimed `h200-dflash-adapter-e00vyqp7gxsr34wrtz` at
`2026-07-26T04:41:12.322366Z`. The durable PID-owned controller is recorded
in `STATUS.json.active_session`, heartbeats the claim through `05:12Z`, and
has crossed `BUILD_STARTED.json` in
`artifacts/sm90a-component-20260726t044127z/`. Its module identity hashes the
source, builder, and include-root tuple, preventing any collision with the
earlier `sm_90` or attempted `sm_90a` artifacts. No candidate CUDA call or
new M32 sample had begun at this snapshot.

**Budget.** The project starts this retained claim at `$0.40` cumulative
exposure. A full 25-minute claim at `$2.45/hour` raises this conservatively
to about `$1.421`, within the `$2.00` reservation. The controller records its
actual elapsed claim cost before any terminal/release.

## 2026-07-26T05:21Z — post-deadline SM90a readmission

**Decision.** The director's fresh admission was consumed by an atomic claim
of `h200-dflash-adapter-e00vyqp7gxsr34wrtz` at `05:21:44Z`. The expired
attempt's raw Ninja record proves a pre-CUDA header integration defect: the
SGLang scaled-MM epilogue needs the CUTLASS `Sm90EVT` and `Sm90Compute`
definitions before the dispatcher is instantiated. The in-image DeepGEMM
CUTLASS tree provides those definitions.

**Amendment.** Restored only that pinned CUTLASS epilogue header before the
unchanged dispatcher and bound `torch.cpp_extension`/Ninja to
`/usr/local/lib/python3.12/dist-packages/deep_gemm`. The source, builder, and
include-root form a fresh content address. No tile, cluster, schedule, scale,
ABI, dtype, workload, or exactness rule changed.

**Execution.** PID-owned durable controller `1575683` started at `05:23:01Z`,
heartbeats the same claim through the absolute `05:55Z` release deadline, and
will build one module then make the one admitted M32 call. M32/M384 remains
conditional on a finite bitwise M32 pass. Starting cumulative exposure is
`$1.6574523726527781`; the controller will persist the elapsed conservative
total before any paid terminal.

**Causal amendment.** The first replacement build stopped before producing a
module because `cutlass/util/packed_stride.hpp` is supplied by TileLang's
utility include tree, not DeepGEMM. The repair request remains preserved in
its artifact. Its PID owner was stopped before release, the same claim was
heartbeated, and one allowed immediate replacement owner (`1576708`) was
started with DeepGEMM as the CUTLASS root and TileLang only as the utility
include root. This is still the same pre-CUDA build operation, not another
scientific sample.

## 2026-07-25 — SM90a pre-discriminator build boundary

**Action.** Atomically claimed the retained H200 at `23:42:34.393429Z`,
materialized the admitted project-local source packet under
`/home/glmrunner/gemma4-fp8-weight-stream-sm90a`, and launched the durable
owner. Its first Docker invocation used `sudo -n docker` and compiled the new
`compute_90a/sm_90a` module request.

**Evidence.** Ninja returned nonzero before a module snapshot,
`M32_SCIENCE_STARTED.json`, or `M32_RESULT.json` existed. The raw build
stdout/stderr, staging manifest, heartbeat, and release records are retained
at `artifacts/sm90a-component-20260725t234241z/`. The Torch wrapper did not
include Ninja's compiler line in its captured stderr; recovering that line is
the sole build-integration diagnostic still needed. A stale prior
`REPAIR_REQUEST.json` rejected creation of the new handshake, so the owner
released the bench to maintenance rather than silently changing or replaying
the scientific operation.

**Interpretation.** This is an ordinary pre-invocation integration failure,
not a scientific result: no candidate CUDA/M32 consumer result was produced
and no sample was consumed. The claim lasted 22.727651 seconds at $2.45/hour;
the conservative cumulative project exposure is `$0.1309096898`.

**Next.** Director re-admission of the retained maintenance bench is required.
Under that new claim, retrieve the Ninja diagnostic, patch only the admitted
SM90a build integration, and run the unchanged one-call M32 discriminator.

**Amendment from retained stdout.** The compiler diagnostic is now recovered:
the pinned CUTLASS tree lacks the explicitly included
`sm90_callbacks_tma_warpspecialized.hpp`. Removed only that redundant include;
the pinned SGLang FP8 dispatcher already provides the referenced schedule
types. The repaired source hash is
`6fbf494585aebb0453c4af9ac17481701e036e5e948e1edac7297d44e2999803`.
This is a content-addressed pre-invocation integration amendment, not a change
to shapes, scales, schedules, or the one-call M32 question.

**2026-07-25T23:57Z terminal.** The re-admitted retained H200 claim tested only
the image-local include/build graph. `/work/sgl-kernel` was absent; the paired
FlashInfer CUTLASS tree then failed on SGLang's required `Sm90EVT`/`Sm90Compute`
fusion ABI; DeepGEMM headers plus the only available packed-stride utility tree
produced the same ABI failure. All three compiler records are hash-bound in
`FP8_WEIGHT_STREAM_SM90A_H200_TERMINAL.json`. No module, candidate CUDA call,
M32 gate, or M384 component was produced; the bench was released to
maintenance. Conservative cumulative project exposure is `$0.40`.

## 2026-07-26T05:59Z — persistent Stream-K scientific terminal

**Offline model and arm.** Source inspection tied the prior M32/M384 reversal
to output-tile widening inside H200's 132-SM persistent grid: the rejected arm
halved independent output work and widened a residency-limited epilogue. The
new arm therefore retained the pinned stock M32/M384 gate/up configs and
introduced exactly one change: deterministic CUTLASS Stream-K decomposition
for down `[M,21504] x [21504,5376]`. The preregistered physical prediction was
a full M32 work queue instead of 84 output tiles and a smoother M384 tail.
`PERSISTENT_GROUPED_PHYSICAL_MODEL.json` and
`PERSISTENT_GROUPED_SOURCE.json` bind the model and source.

**Invalid attempts.** Two ordinary pre-CUDA build defects were preserved and
amended without consuming a sample. First, the immutable image dispatcher
digest differed from an offline sibling snapshot. Second, that image
dispatcher lacked the sibling's scheduler-parameterized helper. The final
source reused the image's exact stock collective types and replaced only
`GemmUniversal`'s scheduler tag project-locally. The corresponding artifacts
and causal amendments are durable; neither attempt produced a module or
science marker.

**Measured result.** Module
`281873ca05896e43453afe1154c2f6e69db7166f73b592c056bbfd77b7978c8c`
compiled for `sm_90a` and entered the unchanged M32 consumer. Gate/up BF16,
GELU product, down-input FP8, and down scale were finite and bitwise equal.
Final BF16 was finite but not bitwise equal (`max |delta| 0.00225830078125`,
relative L2 `0.1942131668329239`). The result is interpretable mechanism
evidence: deterministic Stream-K changed down accumulation/reduction order.
The exactness stop consumed the arm before timings, graph testing, or M384;
none may be replayed.

**Disposition and cost.** Reject the schedule and do not advance it to an
endpoint. The named bench was claimed at `05:49:16Z` and released ready/warm
with no worker at `05:58:51Z`. Conservative cumulative project exposure is
`$2.32`, below the `$5.00` reservation.
