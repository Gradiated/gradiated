# Research log

## 2026-07-28T15:45:00Z — exact M32 SM100 dispatch candidate

Question: what exact source boundary can explain a decision-relevant part of
the valid absolute `0.633995593312477 s/request` B200 runtime-FP8 residual
without replaying the endpoint?

Action: hash-bound only the authoritative absolute dynamic-FP8 terminal,
copied the active installed vLLM source from the immutable local image, and
bound the exact pinned SM100 dispatcher at commit
`6d4a8e6d204a9b2827544003b26321fff62923da`. Derived the six production
linear shapes, hybrid-attention work, KV traffic, tied-head work, nonlinear
logical traffic, and launch/scheduler remainder as mutually exclusive
critical-path categories. The first generator attempt failed before producing
an artifact because it assumed map-shaped accelerator inventory; only that
parser was amended for the actual list schema. A concurrent director
correction then excluded the overwritten BF16 terminal and all paired deltas;
the artifact was rebuilt from the absolute FP8 terminal alone.

Evidence: all 32 valid requests returned 358 tokens, fixing steady decode at
`M=32` for 358 steps. Gemma executes six unique FP8 shapes and 240
transformer GEMMs per step (`85,920` total); every K and N is 128-aligned.
The pinned dispatcher nevertheless sends `17<=M<=64` to a swapped-AB
`128x64x256` tile, leaving 50% M-tail at c32, while the already-compiled
`128x32x128` path is restricted to `M<=16`. The non-overlapping ideal
roofline floors total `5.092405782628124` of the measured
`20.287858985999264` batch seconds; the remaining `15.195453203371141`
seconds is deliberately unattributed because no phase trace or profiler was
retained.

Decision: retain `M32_DISPATCH.patch`, which changes only the dispatch cutoff
to reuse the existing `128x32x128` kernel for `M<=32`. It applies to the
exact source hash and yields the bound post-patch hash recorded in
`B200_FP8_RESIDUAL_DISCRIMINATOR.json`. This is an unmeasured,
semantics-preserving implementation, not a B200 speedup or readiness claim.
After the higher-priority c64 saturation result, the smallest decision is one
stock-versus-patched exact-shape B200 component sample; reject without an
endpoint arm on correctness failure, >5% high-multiplicity regression,
<10% weighted quant+GEMM gain, or <`0.005 s/request` projected saving.

## 2026-07-28T16:05:00Z — six-shape M32 packet sealed

Question: can the queued M32 dispatch discriminator be made executable and
hash-bound without consuming the B200?

Action: implemented `b200_m32_dispatch_component.py` with the six exact
production shapes, deterministic paired arms, real vLLM dynamic per-token FP8
quantization plus `cutlass_scaled_mm`, BF16 oracle metrics, CUDA-event p50
timing, and an in-path `candidate_science_started` marker. Implemented the
claim-gated `b200_m32_dispatch_owner.sh`, which requires an existing project
claim and does not claim or mutate provider resources. Sealed
`PRECLAIM_TERMINAL.json` with hashes, identities, shape multiplicities,
measurement contract, and stop conditions.

Evidence: runner `fb275d75cce1e3d7845b728485f835090a0c70e15957156b5f1b9b2ac20c733e`,
owner `0eaecd7f6a1579f246f57c55f4dd3728c7d5b1062402f9b31931a603f046ec85`,
preclaim `d72d1231f6c5d4f854bdef5532fcbdea1c9b8ea988861c068a351e03beffc6dd`.
Python syntax and preclaim JSON validation passed. No GPU claim, provider
operation, endpoint request, or scientific sample occurred; actual spend
remains `$0.00`.

Decision: packet is durable but not a readiness authorization. Pause until
the `$5` reservation, c96 terminal or safe maintenance handoff, and fresh
director ready envelope are durable.

## 2026-07-28T16:17:00Z — real M32 execution owner launched

Question: can the label-only packet be repaired into a genuinely distinct
stock-versus-patched SM100 production consumer under the funded B200 claim?

Action: read the single director execution envelope, claimed
`b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j` at 16:11:49Z, and rebound the
runner, owner, and preclaim hashes. The owner now preserves the resident
endpoint logs, stops only that resident container to remove contention, clones
the pinned vLLM commit, applies `M32_DISPATCH.patch`, builds a separate vLLM
extension tree, and runs stock and patched fresh containers through the real
`vllm._custom_ops.cutlass_scaled_mm` path. Each arm records its loaded custom
extension path/hash before the first CUDA submission; the final comparator
fails closed unless the extension hashes differ and all six weighted shapes
produce valid terminals.

Evidence: repaired runner SHA-256
`bbd4505a6b2c034f7a2a018e9cb35bbc1bd6093a4b4588fdcab418ef8e349c86`, owner
SHA-256 `466ae0bcdfe6f090df500b341fd769d1846b22c571571ebefee733371653811c`,
and rebound preclaim SHA-256 `4d97a07288d3328b37e1892799850e6000dd47d654d053ef98947910b17de4c1`.
The detached controller is live at
`artifacts/b200-m32-dispatch-20260728t1606z/OWNER_STATE.json`, PID 3323854,
start ticks 137143536, `unit_manager=pid`. Progress crossed source staging
and entered `source_build`; no scientific sample has yet terminalized.

Decision: retain the claim and durable owner through source build and the
bound six-shape measurement. The next terminal is either a negative release
by 17:08Z or a positive component handoff retaining the claim for one
conditional c32 endpoint arm.

## 2026-07-28T16:24:00Z — same-claim pre-science repairs

The first owner exited before science because the pinned image lacked `git`
for setuptools-scm metadata. Repair1 preserved `ATTEMPT_1_PRESCIENCE.json`;
the immediate retry then found a stale patched checkout, repair2 restored the
pinned dispatcher before applying the patch, and repair3 added the generic
setuptools-scm version override. Repair4 and repair5 reached CMake but found
missing `cmake` and then missing `git` for CMake FetchContent. Repair6 added
only `git`, `cmake`, `ninja`, and Git safe-directory configuration inside the
ephemeral build container.

All six attempts are typed `invalid_pre_science_integration_attempt` with
`science_consumed=false`; no CUDA marker, component result, or scientific arm
exists, so no sample was replayed. The repair6 durable owner (PID 3329225,
start ticks 137186216, `unit_manager=pid`) is live and has completed editable
metadata; the actual pinned vLLM build is now running under the same claim.

## 2026-07-28T16:33:00Z — recovery5 git-capable owner launched

The director recovery5 binding stopped the blind owner chain and required a
fresh pinned source/output lineage. The existing B200 claim remains
continuous. Recovery5 is bound to the exact pinned image through
`recovery5.Dockerfile`, which adds only the git/CA/cmake/ninja build
dependencies needed by the pinned source build, and uses a fresh exact-commit
clone before applying `M32_DISPATCH.patch`.

The durable controller is live at
`artifacts/b200-m32-dispatch-recovery5-20260728t1623z/OWNER_STATE.json`, PID
3337978, start ticks 137237894, `unit_manager=pid`, under the 17:27Z watchdog.
Its progress entered `apply_patch_build` at 16:33:12Z. The hash-bound
recovery5 owner, Dockerfile, and preclaim are recorded in `STATUS.json`;
`scientific_sample_consumed=false` and `actual_spend_usd=0.0` remain correct.
No CUDA or component arm has begun. The owner retains the repair handshake and
will continue directly to the still-unconsumed stock/patched six-shape pair
after the fresh build.

## 2026-07-28T17:10:40Z — bounded NVRTC repair preserved pre-science

The repair diagnostic identified `CUDA_nvrtc_LIBRARY=NOTFOUND` inside the
derived image. A same-claim repair request was issued for the narrow
`patched_build` scope with `recovery5_patched_build_retry.sh`; it reused the
fresh patched source and derived image, mounted the retained host CUDA toolkit
read-only, and supplied the missing NVRTC path. The amended command reached
real `ninja` compilation (273 CUDA objects were present before interruption),
but the full editable build could not finish before the remaining terminal
window. It was interrupted before any arm submission.

`REPAIR_RETRY_TERMINAL.json` records exit 255 as
`invalid_pre_science_repair_timeout`, with `science_consumed=false`; the
original recovery5 owner remains live and heartbeating under the continuous
claim. No stock/patched result exists, so no scientific terminal or negative
release was synthesized.

## 2026-07-28T17:17:30Z — reservation gate observed owner terminal

The required grouped snapshot found recovery5 PID 3337978/start ticks
137237894 terminal, with no later progress beyond `apply_patch_build`. The
only terminal artifact is the preserved pre-science repair timeout; no stock
or patched output, CUDA marker, or scientific sample exists. The B200 pool
row was still claimed by this project at the snapshot, but the reservation
gate explicitly forbids lifecycle mutation until the durable $8 reservation
and fresh director envelope exist. `STATUS.json` now clears the stale active
session into `prior_active_session` and records the terminal owner state;
claim, watchdog, image, source, build objects, and provider lifecycle were not
mutated.

## 2026-07-28T17:34:00Z — SM100 continuation incomplete before compilation

The funded SM100 owner launched after the exact B200 claim and passed packet,
claim, predecessor, and retained-state checks. Generation 1 stopped before
science because bind-mounted build/install directories cannot be removed and
its incomplete-release contents argument was not JSON. Repair1 changed only
those boundary paths and used fresh build/output roots. CMake then stopped
before compiler invocation because the retained source requires the explicit
`VLLM_PYTHON_EXECUTABLE` setting.

No CUDA marker, compiler command, stock output, patched output, or component
sample exists. Repair1 emitted `INCOMPLETE_TERMINAL.json` and released the
bench to draining at 17:33:42Z. Conservative cumulative exposure is
`$5.247555268041667` (prior `$4.548077` plus `$0.6994782680416668` for this
claim); no endpoint replay or further lifecycle mutation is authorized until
director revalidation.

## 2026-07-28T17:40:53Z — SM100 repair2 owner launched

The exact B200 was claimed at 17:38:30Z. `b200_m32_dispatch_owner_sm100_repair2.sh` and `PRECLAIM_SM100_REPAIR2_TERMINAL.json` are bound to fresh repair2 roots and the sole localized CMake addition `-DVLLM_PYTHON_EXECUTABLE=/usr/bin/python3.12`. The durable controller launched at 17:40:49Z as PID 3430160/start ticks 137646671 under `detached-owner --unit-manager pid`; its progress crossed binding, claim, predecessor, retained-state, and `sm100_minimum_build`. No science marker or sample exists yet; the owner retains the claim while the SM100-only build and unconsumed stock/patched pair continue.

## 2026-07-28T17:52:16Z — repair2 stopped on compiler architecture fanout

Repair2 claimed the exact B200 at 17:38:30Z, applied only the bound Python executable CMake repair, and completed the retained `_C` build through 71 steps. The compiler audit then found forbidden `-gencode arch=compute_100f,code=sm_100f` and `compute_89,code=sm_89` commands in the generated build, so the SM100-only contract was not met. The owner emitted `INCOMPLETE_TERMINAL.json` with `candidate_science_started:false` and released the bench to maintenance at 17:52:16Z. No stock/patched arm, CUDA marker, or sample was consumed. Preserved diagnostics are `artifacts/b200-m32-dispatch-sm100-repair2-20260728t1734z/sm100-build.stdout` and `.stderr`; cumulative conservative exposure is `$6.153632522375`.

## 2026-07-28T17:59:13Z — direct extension adoption and same-claim consumer repair

The adoption owner verified and installed the completed remote `_C` extension with the bound SHA-256 and skipped compilation. Its first stock arm exposed an ordinary runner/output-root defect (`mkdir(..., exist_ok=False)` against an owner-precreated bind mount); no science marker or sample was consumed. The owner released maintenance, so the pool was re-readied for the authorized same-project repair. Repair2 changed only the output-root setup to let the runner create fresh `stock`/`patched` directories, bound owner SHA `cdc6a4faed5f40fcc89fd690c6cea27e3f7943047ccde71840f774cf2b4e8ad8`, and launched PID 3447762/start ticks 137756759 at 17:59:10Z. Progress crossed the repaired stock boundary; the owner remains live under the claim.

## 2026-07-28T18:51:53Z — corrected B reached stock consumer but failed correctness

The valid-layout repair first fixed the quantizer constraint by quantizing contiguous `[N,K]` weights and transposing the quantized B to `[K,N]`, giving the required `stride(0)==1`. The stock consumer then executed far enough to return a finite first-shape output, but the bound oracle failed: cosine `0.9992967844` versus minimum `0.99999`, normalized RMSE `0.0374981239` versus maximum `0.005`, and max absolute error `0.0050048828` versus maximum `0.01`. The owner stopped before timing and before the patched arm; this is a preregistered correctness incompatibility, not a launcher failure. Diagnostic: `artifacts/b200-m32-dispatch-valid-layout-repair2-20260728t1851z/stock.stderr`. Cumulative conservative exposure: `$6.555344368236111`.
## 2026-07-28T19:04:00Z — paired FP8 oracle owner launched

The `$12` reservation and director paired-oracle envelope were durable. The exact B200 was claimed at 19:00:03Z and a fresh packet was hash-bound without rebuilding or loading the checkpoint:

- `b200_m32_dispatch_component_paired_oracle.py` SHA-256 `9bfa7d21a8f10319f236a46836198e4ec6bf0c08ca39ab4157368e7898cc2e2d`;
- `b200_m32_dispatch_owner_paired_oracle.sh` SHA-256 `fc8afd9844dd7a609ac9ec6b151abcff9da7fbba3d07c8247c90c2e6487b04e6`;
- `PRECLAIM_M32_PAIRED_ORACLE_TERMINAL.json` SHA-256 `265f91b39bbea66abf845270633332f9e94e25f04f01de443243129de704fb0d`.

The durable owner launched through `detached-owner --unit-manager pid` as PID 3530991/start ticks 138143588, with owner state at `artifacts/b200-m32-dispatch-paired-oracle-20260728t1858z/OWNER_STATE.json`. Its grouped snapshot reached `stock_arm` after binding, claim reconciliation, extension adoption, and packet staging; the claim heartbeat remained current. The paired runner saves stock outputs, hashes all four FP8 operands per shape, compares patched directly with stock operands, and stores BF16 comparison only as a diagnostic. No canonical result is promoted until both arms and all finite structurally valid six-shape rows reconcile.
## 2026-07-28T19:18:00Z — float8 raw-byte hash repair handed off

The predecessor's decision-bearing failure was confirmed as `tensor_hash` attempting NumPy conversion of `torch.float8_e4m3fn` before the consumer call. The repaired runner now views contiguous float8 storage as `torch.uint8` and hashes raw bytes without casting or numeric transformation. The replacement packet binds runner SHA-256 `fa5e659a557dd259612a0e9fc4b7593871241dcc5860b35d274816e9c0d883d6`, owner SHA-256 `0f148d6e4c1a21a887e49b3ed163e5f041000c6bcba1012dd8abdcc0ee8139b9`, and preclaim SHA-256 `8d342d33f4b75584e579caefc847581e4db819ae185515633017413b816f340e`.

The shared repair handshake request `paired-oracle-hash-repair` is bound to `stock_arm`. Replacement owner PID 3548624/start ticks 138223231 launched at 19:16:54Z, waited behind predecessor 3530991/138143588, and crossed the predecessor fence only after that exact predecessor exited. It then adopted the unchanged extension, staged the repaired packet, and entered the fresh `stock_arm` output generation at 19:18:05Z under the continuous claim. No release/reclaim, rebuild, checkpoint load, endpoint replay, or provider lifecycle mutation occurred.
## 2026-07-28T19:26:00Z — patched-only CUDA 13 runtime repair launched

The paired stock arm is preserved and hash-verified at `da9166976f2dc840c44e2953607ac7a2912ab4d1f701bcded76f1e7848610a62`, including all six remote oracle tensors. The prior patched attempt was a pre-science loader failure: the retained `_C` extension required `libcudart.so.13` and the CUDA-12.9 derived image did not provide it.

The replacement owner binds only `/usr/local/cuda-13.0/targets/x86_64-linux/lib/libcudart.so.13.0.96` to `/usr/local/lib/libcudart.so.13` and prepends `/usr/local/lib` to `LD_LIBRARY_PATH`; it does not replay stock, rebuild, load the checkpoint, or broaden the CUDA mount. Owner SHA-256 is `7c211d6f692948aeb967144e130ba91ab339aa108a476952a0be8e1f30a2f14e`; preclaim SHA-256 is `d1343b3dedbb142b1ad85a458cac1d948cb57ca18d572a2225dd29a934e1334b`.

Durable owner PID 3561496/start ticks 138280394 launched at 19:26:26Z under the original claim, validated the preserved stock root, staged the packet, and entered `patched_arm` at 19:26:30Z. No patched result or paired scientific terminal is available yet.

## 2026-07-28T22:48:58Z — static-persistent M32 consumer bound

Question: after the consumed M16 `128x32x128` SwapAB cutoff regressed the
weighted exact six-family path by 3.5324%, what materially distinct SM100 M32
schedule can isolate a remaining physical limiter without changing the
qualified dynamic-FP8 representation?

Action: traced vLLM commit `6d4a8e6d...` through CUTLASS 4.2.1 and found that
the stock `void` GemmUniversal scheduler resolves to dynamic
`PersistentTileSchedulerSm100` Cluster Launch Control. Implemented
`M32StaticPersistentGemm`, which reuses the exact stock
`128x64x256`, cluster `4x1x1`, SwapAB mainloop and scaled epilogue but replaces
only that scheduler with `StaticPersistentScheduler`. Added a single-process
runner that feeds stock and candidate the same official per-token activation
and per-tensor online-weight FP8 tensors, synchronizes first calls separately,
requires bitwise BF16 equality, alternates 31 warm CUDA-event pairs, and
atomically checkpoints each of the six families. Added a cold-start owner that
stages content-addressed source, builds only `sm_100f`, retains claim and
heartbeat through hash-bound repair generations, resumes only an incomplete
family, validates the complete provenance/oracle ledger, and then releases.

Evidence: `B200_FP8_M32_NEXT_MECHANISM.json` SHA-256
`ad3c01d535a7d044b3848efc7b2c34d5a256950bae1696b3730b60a9c82e7442`
binds the consumer, builder, runner, owner, Dockerfile, causal model, exact
geometry, predicted counters, request projection, lifecycle, and stop rule.
Python compilation, JSON parsing, three behavioral contract tests, and both
non-CUDA validation entrypoints passed. No GPU was claimed and no provider
lifecycle was mutated; this is executable offline readiness, not a measured
B200 result.

Interpretation: uniform 42-336-tile dense families offer little dynamic
load-balance value, while 37.5-83.8 microsecond stock calls can expose CLC
bookkeeping. The candidate predicts unchanged tensor instructions and DRAM
bytes with 1-5% lower SM cycles if this limiter is real, corresponding to
`0-0.004 s/request`; flat or slower timing falsifies it.

Next: a director may bind and provision one exact B200 inside the remaining
`$6.27`, then launch the owner through shared `detached-owner --unit-manager
pid`. Stop without endpoint work on any bit mismatch, >5% family regression,
non-positive weighted saving, or projected saving below `0.001 s/request`.

## 2026-07-28T23:00Z — bound static-persistent component owner launched

The exact B200 bench was atomically claimed at `23:00:09Z`, inside the
director's `23:03Z` fence. The shared controller-host `detached-owner` is live
as PID `3692757` / start ticks `139562695`; its durable unit is
`artifacts/b200-m32-static-20260728t2258z-controller/OWNER_STATE.json` and
the owner has crossed `cold_source_reconciliation`. `STATUS.json` records the
same active-session identity, exact bench, bound mechanism digest
`ad3c01d5…`, and `23:50Z` deadline. The owner retains the claim, heartbeat,
source/image staging, build, component execution, retrieval, scoped repair,
and final release. No component result is available yet.

## 2026-07-28T23:15Z — retained build repair accepted

The first build stopped before component CUDA submission because the derived
runtime image omitted CUDA development headers, beginning with `cusparse.h`.
The raw Ninja stderr and diagnostic are preserved in the active artifact root.
Repair `m32-static-1` changes only the derived-image Dockerfile, adding CUDA
13 development headers; its dynamic remote build verified cuSPARSE, cuBLAS,
and cuSOLVER headers. The live owner accepted the hash-bound `source_stage`
request and crossed into candidate build generation 2 at 23:15:11Z while
retaining the original claim. No scientific sample has been consumed.

## 2026-07-28T23:22Z — retained CUDA-ABI/build repair accepted

The repaired header image exposed the next pre-science incompatibility: CUDA
13 headers conflicted with the resident CUDA 12.9 `nvcc` driver typedef ABI,
and the pinned vLLM helper is globally scoped rather than `vllm` scoped. Repair
`m32-static-2` switches only the derived headers to CUDA 12.9 and adds a
compile-time namespace alias in the builder; it leaves the candidate source,
static-persistent scheduler, tile, mainloop, operands, and scales unchanged.
The dynamic image check passed, the live owner accepted the hash-bound repair,
and it crossed into candidate build generation 3 at 23:22:44Z with the original
claim still heartbeating. No component arm or sample has been consumed.

## 2026-07-28T23:24Z — retained compatibility-header repair accepted

The CUDA 12.9 build reached a new pre-science parse error because the forced
compatibility header imported the full scaled-MM dispatch before ATen. Repair
`m32-static-3` now imports only the pinned vLLM common header that defines the
global SM100F guard, preserving the exact candidate source and scheduler-only
mechanism. The same owner accepted the hash-bound `build` request and entered
candidate build generation 4 at 23:24:25Z; its original claim remains current.

## 2026-07-28T23:29Z — retained TorchInductor-cache repair accepted

Build generation 4 completed, but the component stopped before invocation when
vLLM's TorchInductor import called `getpwuid` for the numeric container user.
There was no invocation state, terminal, or result row. Repair
`m32-static-4` sets `TORCHINDUCTOR_CACHE_DIR=/tmp/torchinductor` in an image
derived from the same retained CUDA-12.9 image; a real vLLM import under that
numeric user passed. The owner accepted the repair and crossed into candidate
build generation 5 at 23:29:34Z under the original heartbeat and claim.

## 2026-07-28T23:36Z — exact static-persistent launch incompatibility retained

Repair `m32-static-5` created only the missing zero-request resume directory
and re-entered the already-built consumer; it did not rebuild or change the
candidate. The retained component then reached `sliding_qkv`, completed the
stock first call, and recorded both candidate CUDA/science-start markers. Its
first static-persistent candidate launch failed in CUTLASS cluster launch with
`cudaErrorInvalidConfiguration` before an exactness comparator result or any
completed row. `INVOCATION_STATE.json` and `REPAIRABLE.json` are durable and
show no completed family, so this is not a valid paired sample. The exact
failing candidate source is bound by mechanism `ad3c01d5…`; an unchanged
consumer retry would replay the same failed call, while a source-level launch
correction requires a director-issued rebind. The original owner and claim
remain live at repair `m32-static-6` for bounded disposition.

The persisted generation-6 markers localize the incompatibility: the exact
M32 geometry has one 128-row M tile, while the bound candidate reports a
4x1x1 cluster. The first `cudaLaunchKernelExC` returns invalid configuration.
That is a physical inference from the bound geometry and runtime error, not a
timing or correctness result. No unchanged `consumer:resume` request was sent:
it would repeat the same post-CUDA launch. A geometrically legal correction
would necessarily change the bound candidate source digest and requires a
director rebind.

## 2026-07-28T23:53Z — zero-grid cause and geometric rebind candidate

Question: explain the SM100 invalid launch and prepare the smallest offline
source correction without submitting repair generation 6 or touching the
claimed bench. Source evidence closes the immediate mechanism: pinned vLLM
default-constructs `KernelHardwareInfo`, so `sm_count=0`; CUTLASS 4.2.1 static
persistence uses that field to size its physical grid and derives
`dim3(4,0,1)`, which reaches `cudaLaunchKernelExC` and is rejected as an
invalid configuration. Stock dynamic persistence does not use this
hardware-sized physical grid, matching the observed stock-first-call success.

Action: added
`m32_static_persistent_geometric_rebind_extension.cu` (SHA-256
`1d1f5aba004d9e33e14a0c548eca2ea8c0e5f326fc60b1dac2334e482b30e425`).
It binds `sm_count` from PyTorch's cached device properties before CUTLASS
argument construction and adds fail-closed nonzero-grid, cluster-divisibility,
and shared-memory guards. The device kernel retains the same 128x64x256 tile,
4x1x1 cluster, static scheduler, SwapAB mainloop, scaled epilogue, operands,
scales, BF16 output, and `m32_static_persistent` ABI used by the unchanged
runner comparator.

Evidence: `B200_FP8_M32_GEOMETRIC_REBIND_CANDIDATE.json` (SHA-256
`add989a37128c2b517a6d176e1ca572d0ae3c71faf694a616dc23fb6f6f951ec`)
hash-binds the failure, pinned sources, candidate, all six geometries, and
later owner/runner entrypoints. At the 148-SM B200 reference, the legal
physical grids are 4x32 for sliding QKV, 4x11 for each 5,376-wide output,
and 4x33 for global QKV and gate-up; every grid is cluster-divisible and
210,944 B/CTA is 21,504 B below the 232,448 B opt-in block limit. This is
analytical/source-backed evidence, not a build, CUDA, correctness, timing, or
endpoint result.

Interpretation and next move: a later director may bind this distinct source
to the existing static owner and runner. First run only the synchronized
sliding-QKV stock/candidate calls; stop on any identity, launch, finite, or
bitwise mismatch before admitting the other five families. PID 3692757 was
not signaled, replaced, or repaired during this turn; it was live at intake
and exited naturally after its recorded 23:50Z owner deadline.

## 2026-07-29T00:03Z — geometric-rebind packet completed after claim fence

Action: adapted only the static scheduler owner for the new geometric source
name, a generated runtime manifest, a fresh remote output root, and read-only
reuse of the prior resident vLLM/CUTLASS source trees. The generated manifest,
owner, runner, builder, Dockerfile, source, and director binding are hash-bound
in PRECLAIM_B200_FP8_M32_GEOMETRIC_REBIND_TERMINAL.json.

Evidence: local Python compilation, manifest JSON parsing, and the owner's
local contract validation passed. The packet completed at 00:03:52Z; the
available B200 was still unclaimed, but the binding's 00:03:30Z claim fence
had passed. No claim, SSH GPU operation, CUDA call, sample, endpoint, or
provider lifecycle mutation occurred.

Interpretation: this is a typed lifecycle boundary, not a result about the
runtime-SM-count correction. The director must issue a replacement lifecycle
that fits within the existing watchdog before this exact packet may execute.

## 2026-07-29T00:11Z — geometric runtime-SM-count rebind measured positive

Question: does supplying live B200 SM count make the exact M32
static-persistent FP8 consumer legal and beneficial without changing the
scientific contract?

Action: the replacement-bound owner reused the resident image and source
trees, built the geometric-rebind module, first ran the staged sliding-QKV
stock/candidate calls, then continued the other five families only after the
finite full-output BF16 bitwise gate passed.

Evidence: the retrieved terminal at
artifacts/b200-m32-geometric-rebind-20260728t2356z/retrieved/TERMINAL.json
(SHA-256 0ae7045789efd8dd33093aff7c0c72ea0ba7995c66a6c89a2e445d71f87775cf)
has six complete bitwise-equal rows, 31 alternating profiler-off CUDA-event
pairs per family, a 10.30% multiplicity-weighted quant-plus-GEMM p50 gain
(1.21024 ms/decode step), and a projected 0.0135396 s/request saving. The
candidate module is 6940d416…, built from geometric source 1d1f5aba….

Interpretation: the zero-grid explanation was sufficient: the runtime
SM-count correction produces a legal exact candidate and clears every
component stop rule. The binding does not authorize endpoint measurement, so
this is a positive director-endpoint disposition, not an endpoint claim.
The scientific terminal was recovered before release. The owner first tried
the obsolete pool condition available; its maintenance fallback released the
otherwise healthy bench. No replay or additional GPU work is authorized.

## 2026-07-29T00:31Z — endpoint owner pre-science stager repair

Action: materialized the director-bound checkpoint under this project as a
read-only hard-linked snapshot, authored the endpoint owner and pair runner,
and launched the authorized durable owner. It claimed the B200 and entered
checkpoint staging without a server, CUDA call, or endpoint request.

Evidence: the owner recorded FileNotFoundError before transferring checkpoint
bytes because this controller lacks rsync. OWNER_INCOMPLETE.json preserves that
pre-science diagnostic. The owner released the pool claim to maintenance; the
researcher did not re-ready, reclaim, or alter the provider.

Interpretation: the endpoint sample remains unconsumed. The owner now uses a
manifest-driven resumable byte-range SSH transfer rather than rsync, but its
changed hash revokes READY. A director must inspect and re-ready the bench and
rebind the amended packet before the single endpoint pair can execute.
## 2026-07-29T00:39Z — pre-science endpoint owner repair bound

Question: can the unconsumed B200 c32 endpoint pair resume after the zero-byte controller failure?

Action: bound `DIRECTOR_B200_STATIC_SCHEDULER_ENDPOINT_PRE_SCIENCE_OWNER_REPAIR_20260729T0038Z.json`; amended only `b200_static_scheduler_endpoint_owner.py` to resolve and require absolute `ssh`, `scp`, and `tail` paths, persist command-plus-traceback diagnostics, and retain the claim through fresh repair-handshake generations for recoverable defects. Re-emitted runtime/preclaim bytes.

Evidence: `/usr/bin/ssh`, `/usr/bin/scp`, `/usr/bin/tail`, identity key, and known-hosts file exist; Python compilation passed. The original scientific binding, checkpoint manifest, runner, and candidate source remain unchanged. The endpoint pair is unconsumed.

Next: publish the repaired READY packet as the last packet mutation and launch the durable owner on the reopened exact B200.
## 2026-07-29T01:22Z — checkpoint-manifest finalize repair held

Question: can the live retained owner safely retry its checkpoint stage after all bound checkpoint files arrived?

Action: inspected `REPAIR_DIAGNOSTIC_endpoint-pre-science-1785288152-1.json`. Patched only the owner to stage `model-files.sha256` atomically and verify it against the bound manifest digest, rather than comparing its digest with the final model shard digest.

Evidence: the live owner's loaded retry entrypoint is monolithic; it has already loaded the faulty `stage()` function. A request would re-enter that unchanged function and deterministically repeat the same pre-science failure. The endpoint pair and CUDA remain unconsumed; the claim/heartbeat remain live.

Interpretation: the corrected bytes require a replacement-owner or live-code-reload handoff. The current directive forbids stopping or replacing this owner, so no unsafe repair request was submitted.
## 2026-07-29T01:26Z — repair-request hot-reload falsified

Question: does the retained live Python owner consume amended owner bytes after a hash-bound repair request?

Action: submitted the first-generation checkpoint-stage repair request without stopping or replacing the owner.

Evidence: the owner consumed the request at `01:25:02Z`, re-entered `checkpoint_stage`, and emitted fresh `endpoint-pre-science-1785288360-2` at `01:26:00Z` with the identical stale final-manifest command. Remote checkpoint has eight model files and no staged manifest; no CUDA, container, or endpoint request started.

Interpretation: this owner is not a live-code-reload repair executor. A same-claim live reload or a director-bound owner transition is required; another identical repair request would only replay the invalid pre-science operation.

## 2026-07-29T01:34Z — retained-claim manifest reload launched

Action: bound the director's retained-claim manifest-reload packet, then stopped only the verified predecessor PID `3761421` (start ticks `140194293`) and launched the hash-bound replacement through `detached-owner` without a pool claim, release, or reclaim.

Evidence: replacement PID `3793460`, start ticks `140480999`, adopted the original `00:43:20.343760Z` B200 claim, emitted `retained_claim_adopted` then `checkpoint_stage`, and advanced the pool heartbeat to `01:34:12Z`. READY SHA-256 is `076b0758db8eff54ce385ebcec0b44456a52680db01c10ac3298bf802889317c`. No terminal, CUDA invocation, or endpoint request exists.

Next: the durable owner will reuse verified checkpoint shards, atomically install only `model-files.sha256`, then continue to the production build and the still-unconsumed single stock/candidate c32 pair.

## 2026-07-29T01:40Z — retained build-reuse repair requested

Question: can the production dispatch resume without rebuilding an already verified exact SM100 module from the incomplete resident source tree?

Action: diagnosed the pre-science build as missing CUDA development headers, then missing qutlass headers in the source snapshot. Staged a read-only host CUDA header view for diagnosis and amended the build entrypoint to reuse only the content-addressed resident `build-1` module after checking its candidate digest, `sm_100f` code, and required scheduler metadata. The real pinned-container build entrypoint passed against the complete retained packet; its repair request is bound at `endpoint-pre-science-1785288862-1`.

Evidence: reused module SHA-256 `6940d416…`, candidate SHA-256 `1d1f5aba…`, and build manifest SHA-256 `18f0d318…`; smoke output is `repair-build-reuse-smoke.stdout` SHA-256 `05253b5…`. No endpoint request, CUDA scientific marker, or sample was consumed.

Next: live PID `3793460` will consume the request and resume only checkpoint/build followed by the sole c32 stock/candidate pair.

## 2026-07-29T01:49Z — CUDA 12.9 build-environment repair passed

Question: can the retained pinned vLLM build container compile the unchanged B200 candidate when supplied only the CUDA development headers matching its nvcc?

Action: replaced the CUDA 13 packet headers with the resident derived image's read-only CUDA 12.9 header tree and corrected the generated compatibility header to include the existing pinned `/vllm/csrc/cutlass_extensions/common.hpp` directly. Proved `build-1` had no `BUILD_MANIFEST.json` before removal. The exact container smoke built a fresh manifest containing only `sm_100f`.

Evidence: smoke manifest SHA-256 `6ad8911c…`, candidate SHA-256 `1d1f5aba…`, and output module SHA-256 `75cdc90f…`; no CUDA scientific marker or endpoint request was written. Owner PID `3793460`/start ticks `140480999` and the original `00:43:20Z` claim were rechecked immediately before repair publication.

Next: submit the scope-matched repair request so the live owner resumes the production build and sole endpoint pair.

## 2026-07-29T02:21Z — endpoint first divergence localized; promotion closed

Question: does retrieved evidence exonerate the static scheduler from the sole
semantic mismatch in the consumed endpoint pair?

Action: without a GPU claim or replay, read the admitted pair terminal,
request-10 arm requests/responses, and immutable runner once into a
content-addressed offline capture. Reconstructed the runner's exact
`choices[0].token_ids` concatenation and compared the complete 32-row request
and token-hash ledgers.

Evidence: pair SHA-256 `afe8b547…` is verified. All 32 arm request hashes
match; request 10 is byte-identical at SHA-256 `7b1eef46…` with
`temperature=0` and seed `20260738`. Thirty-one token hashes match. For
request 10, both raw SSE streams reconstruct 358 IDs and reproduce the
terminal hashes exactly. Completion position 21 (one-based) is the only
difference: stock token `1788`, candidate token `236814`; the preceding 20
and following 337 IDs match. The candidate remains 0.0552904% slower.

Interpretation: raw-response agreement rules out a terminal hashing/parser
artifact, and configured stochastic sampling was disabled. The retrieved
evidence has no same-arm A/A or logits, so numerical endpoint nondeterminism
cannot be excluded; consequently scheduler causality is not proven. It also
does not provide a scope-matched explanation that exonerates the scheduler.
`B200_STATIC_SCHEDULER_ENDPOINT_FIRST_DIVERGENCE.json` SHA-256 `6913cda7…`
therefore rejects promotion fail-closed. The pair remains consumed, provider
cleanup remains verified, and no paid claim authority remains.
