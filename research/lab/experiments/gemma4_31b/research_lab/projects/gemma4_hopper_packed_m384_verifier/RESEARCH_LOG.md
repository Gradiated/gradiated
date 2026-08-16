# Research log

## 2026-07-26 — exact M384 consumer and packed online-softmax intervention bound

Question: can a real Hopper decomposition replace the stock 255-register,
one-CTA/SM M384 verifier attention path without repeating the rejected
`BLOCK_M` sweep?

Action: materialized the pinned SGLang `extend_attention.py` bytes locally and
bound the exact c32 consumers: 384 BF16 query rows, 50 local
Hq32/Hkv16/D256/window-1024 layers, and 10 global Hq32/Hkv4/D512/context-4214
layers consuming shuffled page-size-1 E4M3 KV directly. Implemented
`packed_m384_attention.py`: M16 WGMMA-eligible tiles split prefix context into
512-token work partitions, persist exact `(max, normalizer, output)` state,
and merge it in partition order. The candidate has no fallback and the paired
runner consumes every output, verifies tolerance, CUDA-graph replay, exact
2/9-partition dispatch, and alternating p50/p95 timing.

Evidence: the physical contract is `EXPERIMENT_CONTRACT.json`; the immutable
source list is `INPUT_MANIFEST.json`; the bound container invocation is
`EXACT_START_COMMAND.json`. Direct KV intensity is analytically 24 useful
FLOP/byte. Partial-state traffic adds approximately 9.4% local and 10.3%
global bytes while raising stage-1 work from 1,024 stock CTAs/layer to 2,048
local and 9,216 global CTAs. Two CPU tests prove the online-softmax merge
matches a single state and correctly rescales prior output when the running
maximum changes. Python compilation, JSON validation, and manifest hashes
pass. No CUDA kernel or scientific arm has run.

Interpretation: exact page-size-1 shuffled `kv_indices` invalidate contiguous
TMA for the dominant KV transfer; TMA of only the small Q tile is not the
causal intervention. The high-value test is therefore direct paged FP8 reads
plus context partitioning and exact online-softmax reduction. Target execution
must decide whether lower register residency and extra grid waves exceed the
partial-state traffic and merge cost.

Next move: the only registered H100 is now `maintenance` and explicitly
reserved for `h100_hybrid_attention_kernel_mechanism`, so this project did not
claim or touch it. After director readmission, atomically claim an authenticated
H100, stage only the manifest bytes, run the exact command under one durable
claim/heartbeat owner, repair ordinary compile/API defects in place, and
continue to the paired measured component terminal. Spend remains `$0`.

## 2026-07-26 — retained H100 pre-science staging failure

Question: execute the rebound spill-free V2 packet on the sole released H100.

Action: atomically claimed `h100-paged-fp8-e00mkpyvykfak0bg1m` at
`16:47:27Z`, verified the release digest and all five manifest members, and
started a PID-managed claim owner. The first owner had a local inventory
map/list controller defect; the one immediate same-claim replacement repaired
that and created the remote root before immutable packet SCP. The replacement
then failed in the remote shell hash expression with `test: too many
arguments`. It was not relaunched again.

Evidence: `REMOTE_PRE_SCIENCE_RETRIEVAL.json` proves the remote
`INVOCATION_STATE.json` and `PACKED_M384_VERIFIER_RESULT.json` are absent.
`RECOVERABLE_DIAGNOSTIC.json`, `OWNER_TERMINAL.json`, and the hash-bound
initial repair handshake preserve both failures. The remote contains only
`packet.tar` and `packet.tmp` members; no Docker container or CUDA candidate
ran. The claim was released to maintenance at `16:51:54Z`; charged exposure is
`267.294463` seconds at `$2.95/h`, conservatively rounded to `$0.22`.

Interpretation: this is a typed pre-science staging integration failure, not
evidence about the packed M16/512 direct-E4M3 mechanism and not a consumed
sample. The warm image and partial immutable packet remain for recovery.

Next move: director should admit one fresh retained repair generation with a
corrected manifest checker, preserve the existing `packet.tmp`, and continue
with staging followed directly by the unchanged exact command.

Amendment: `run_h100_owner.py` now joins the per-member hash predicates with
`&&` rather than passing them as one `test` invocation. It was syntax-checked
locally but deliberately not relaunched after the bounded corrected retry.

## 2026-07-26 — packet-stage recovery exhausted pre-science retry

Action: under the director's recovery binding, replaced the shell test with
an argument-safe Python per-file staged-manifest check. It bound the manifest
itself, rejected unsafe paths/symlinks, and promoted the existing matching
remote `packet.tmp` to `packet` without transfer. The first recovery owner
then exposed an SSH `-c` argument-boundary bug; its one same-claim replacement
passed staging but failed before Docker because `artifacts/h100-component` did
not exist for stdout/stderr redirection.

Evidence: `STAGING.json` records `remote_state: reused_packet_tmp` and
`REMOTE_PRE_SCIENCE_RETRIEVAL_RECOVERY2.json` proves the invocation marker and
scientific terminal are absent. No CUDA work or scientific sample occurred.
The second claim ran `121.310381` seconds at `$2.95/h`, conservatively adding
`$0.10` to cumulative project exposure (`$0.32`). It was released to
maintenance at `16:59:15Z` after the bounded corrected retry failed.

Interpretation: the V2 packet and the stage repair are validated operationally;
only the controller's artifact-directory setup failed. The owner now creates
that directory before the unchanged exact command, source hash
`c5294f2c4d81c5811cfc2646217ec80ed252fda31d4322aa76622d64db3e645d`.

Next move: a fresh director recovery may reuse the verified remote packet and
run the sole unconsumed paired component sample without restaging.

## 2026-07-26 — remote-command recovery bound, awaiting readmission

Action: applied `DIRECTOR_H100_REMOTE_COMMAND_RECOVERY_20260726T1700Z.json`
without claiming the maintenance H100. `run_h100_owner.py` already created the
bound artifact directory; amended its SSH invocation so `bash -lc` and the
entire payload are delivered as one `shlex.join(...)` remote command.

Evidence: `REMOTE_COMMAND_REPAIR.json` binds the director release and final
owner source hash `88f29d980ec819c79fa110085b9e6ea2e272ac715127afc40fd8a955fbc49a18`.
Python compilation and an AST/source contract check passed. The persisted
packet state remains `reused_packet_tmp`; no remote guest was contacted and no
additional spend or sample occurred.

Next move: wait for the director to transition the maintenance H100 to ready,
then make the one admitted claim and run the unconsumed paired component sample.

## 2026-07-26 — readmitted c32 endpoint owner launched

Action: implemented the controller-local `run_endpoint_owner.py`, hash-bound it
in `ENDPOINT_OWNER_BINDING.json` to the 17:41Z readmission, and launched the
prescribed PID-managed detached owner. The owner atomically claimed only
`h100-paged-fp8-e00mkpyvykfak0bg1m` at `17:47:45Z` and is staging only the
project-local endpoint manifest into its isolated remote root.

Evidence: `ENDPOINT_OWNER_STATE.json` records PID `1956275`, start ticks
`120408264`, and `unit_manager: pid`; the first grouped snapshot proved it is
live, has a successful claim heartbeat, and crossed into `staging_copy` for
the bound 49,784,788,364-byte checkpoint shard. No endpoint science-start
marker or candidate CUDA result exists yet.

Next move: the durable owner verifies and atomically promotes the immutable
stage, then runs exactly one profiler-off matched c32 control/candidate pair;
it retrieves the compact terminal and releases to maintenance by 19:00Z, or
retains the claim through its bounded repair handshake if an ordinary
integration boundary occurs.

## 2026-07-26 — offline SM90 compile falsification and packet rebind request

Action: compiled the released v1 source to SM90 CUBIN in the pinned image.
`cuobjdump` proved context partitioning alone retained the full-D accumulator:
local used 254 registers/thread and global used 255 plus a 272-byte stack
frame. Replaced it with `packed_m384_attention_v2.py`, which persists BF16 QK
scores and exact partition max/normalizer state, merges the online-softmax
state, and lets 64-feature value consumers read direct paged FP8 V without a
full-D live accumulator.

Evidence: `artifacts/OFFLINE_SM90_COMPILE.json` binds every final PTX/CUBIN
identity. The local producer is 128 registers/thread, local/global value
consumers are 168, merges are 24/32, and the global producer is 239 with no
stack or local spill. Dynamic shared memory is 40,960/81,920 bytes for the
local/global score producers and 10,240 bytes for value consumers. The
analytical cost is extra BF16 score traffic equal to 24.9% of local and 21.4%
of global direct FP8 KV bytes.

Interpretation: v1 is a physical negative and should not consume the released
H100. V2 keeps the exact scientific question and all acceptance gates, but the
director release freezes v1 hashes. `DIRECTOR_REBIND_REQUEST.json` therefore
requests a mechanism-preserving same-project packet rebind. No claim, guest
contact, CUDA execution, sample, or spend occurred.

## 2026-07-26 — H100 exact-consumer paired component positive

Action: claimed the director-released H100 under the hash-bound remote-command
recovery, reused the verified resident packet without restaging, and ran exactly
`python3 run_h100_owner.py` under a PID-managed owner. The owner retrieved the
terminal and released the bench available.

Evidence: `artifacts/h100-component/PACKED_M384_VERIFIER_RESULT.json`
(`sha256:5b32a5c28ada71d88ed4e30201ef43ad91432c0597a1872772ede9c8e99e9e88`)
is `component_positive`, correct, and exact-work-valid on an NVIDIA H100 80GB.
The local D256 case reduced p50 from 1.39248 to 0.491808 ms (64.68%); global
D512 reduced p50 from 3.270368 to 2.910112 ms (11.02%). Their prescribed
weighted p50 reduction is 47.53%, projecting to 50.59 ms saved per qualified
request. Both cases passed finite, tolerance, output-consumption, direct-FP8,
and CUDA-graph replay gates.

Interpretation: this is one consumed positive exact-consumer component sample,
not an endpoint measurement. The 21.286-second claim adds `$0.02` at `$2.95/h`;
cumulative conservative project exposure is `$0.34`.

Next move: director may admit the cheapest compatible endpoint continuation;
do not replay this settled component sample.

## 2026-07-26 — production c32 endpoint integration bound offline

Question: can the measured V2 local/global consumers be connected to the
qualified endpoint without changing their kernels or silently falling back on
target-verification work?

Action: traced pinned SGLang v0.5.13
`TritonAttnBackend.forward_extend` through its window-trimmed local
`window_kv_indptr/window_kv_indices` and full global paged metadata into
`extend_attention_fwd` and the unchanged model residual consumer. Materialized
the exact 62,578,655,208-byte checkpoint as project-local read-only hardlinks,
plus byte-identical qualified runner, entrypoint, decode-equivalent LM-head,
token observer, and runtime-source snapshots. Integrated the three measured V2
Triton kernels unchanged; the endpoint-only adapter uses fixed 1,024-local and
4,608-global score capacities, covering the exact
`4,214 + 358 + 12 = 4,584` global bound without per-step workspace allocation.
Built one matched profiler-off control/candidate driver with persisted control
producer state, raw SSE and cumulative target/emitted token comparison, exact
cache/request accounting, 50:10 local/global route multiplicities, and an
immediate error on any target-verification fallback.

Evidence: `ENDPOINT_READY.json`
(`sha256:64c738f61a7a031a3b28fbcabee3a9fa8ebfb3e88541426ee8e1c70cdfe0a8d3`)
binds the exact outer and per-arm commands, SGLang image/commit, checkpoint,
workload request hashes, runtime patch, expected terminal, spend envelope, and
all gates. `inputs/endpoint/ENDPOINT_INPUT_MANIFEST.json`
(`sha256:c368088b8c8bdb88fa44a564fc8d36e87dafb4984b29718c12c209d49912e44e`)
binds every staged byte. AST hashes prove `_score_partition_kernel`,
`_merge_state_kernel`, and `_value_consumer_kernel` are identical to measured
V2. Six local tests pass, including fail-closed token mutation and fallback
mutations. Rehashing the full project-local checkpoint matched all eight
qualified file identities.

Interpretation: endpoint integration is ready for the first target-GPU call,
but this is intentionally not endpoint evidence. The current director binding
still forbids a claim until it consumes `ENDPOINT_READY.json`; inventory remains
unclaimed and no GPU, provider, spend, or endpoint sample was consumed.

Next move: after exact director readmission, claim only the retained H100,
stage from the project-local manifest without resolving shared paths, and run
the single bound matched c32 pair. Preserve the settled component without
replay.

## 2026-07-26 — endpoint graph incompatibility terminal

Action: retained the live claim owner through its repair handshake, pulled the
bound SGLang image, archived the zero-request partial output root, and ran the
unchanged remote endpoint command against the verified staged checkpoint.

Evidence: the control producer completed once and is preserved in
`artifacts/endpoint/endpoint-repair2-artifacts.tar.gz`, but its raw SSE lacks
the requested token-ID field, so its comparator rows retain
`returned_token_ids: 0`. The candidate server then failed during CUDA-graph
initialization, before `candidate_science_started`, with
`packed_m384_exact_shape_required`. `REPAIR_TERMINAL.json` binds the raw
controller stderr, candidate log, input image-pull proof, compact archive, and
the no-candidate-request classification. The owner retrieved the repair
request and released the still-safe bench to maintenance at 18:24:15Z. Its
continuous claim cost was `$1.794908`; cumulative project spend is
`$2.134908`, below the `$8` ceiling.

Interpretation: this is an informative endpoint incompatibility for the
hash-bound implementation: it cannot satisfy the required CUDA-graph fixed
production path. It is not a measured endpoint gain/loss and does not consume
the candidate request arm. Altering the route/kernel to special-case graph
capture would change the admitted endpoint identity, while the completed
control producer must not be replayed.

Next move: director disposition only. Preserve the staged checkpoint, image,
raw control producer, and failure archive; any successor needs a newly bound
graph-compatible candidate and token-ID observer contract.

## 2026-07-26 — graph-layout repair and persisted control oracle bound

Question: can the graph-capture mismatch be repaired without changing the
three positive V2 kernels, replaying control, or changing the exact c32
scientific geometry?

Action: compared the admitted router, rejected wrapper, pinned
`TritonAttnBackend.forward_extend`, and all kernel index expressions. The
backend supplies shaped Q/O views and explicitly contiguous K/V; all V2
kernels already receive token/head strides and assume only unit feature
stride. Replaced the wrapper's full-contiguity requirement with that exact
rank-3/unit-feature-stride contract. Stream-joined the preserved raw SSE
response IDs to token-event RIDs and ordered scheduler deltas, then bound a
candidate-only resume and PID-managed retained-repair owner.

Evidence: `GRAPH_CAPTURE_REPAIR_READY.json`
(`sha256:dccf35e742b0e645c271a5b2fe762817c9bf501d9d1861ba3b5a5ac31a4b7cdf`)
binds the repair, delta manifest, exact start command, and owner.
`inputs/endpoint/CONTROL_TOKEN_ORACLE.json`
(`sha256:5ae3ee1ef81641e778a08063d56cd62c4659470b2da695d8d8bc3e27779dbf7b`)
contains 32 unique request hashes/RIDs and exactly 358 emitted token IDs per
request from the persisted producer. AST hashes for `_score_partition_kernel`,
`_merge_state_kernel`, and `_value_consumer_kernel` remain identical to the
measured V2 source. Seven offline consumer, fail-closed, oracle, and AST tests
pass. No GPU was claimed, no control/component/candidate request replayed, and
spend remains `$2.134908`.

Interpretation: the graph failure was a wrapper-layout assumption, not a
kernel or geometry negative. The H100 remains maintenance-bound; readiness is
not endpoint evidence.

Next move: director consumes the exact readiness digest into
`GRAPH_CAPTURE_REPAIR_READMISSION.json`; only then launch the bound durable
owner for CUDA-graph discovery and the sole unconsumed candidate c32 request,
with release by 19:55Z.

## 2026-07-26 — readmitted owner claimed; pre-submission staging repaired in place

Question: can the admitted candidate-only CUDA-graph path reach its first
real discovery call without replaying the persisted control or component?

Action: launched the exact PID-managed command from
`GRAPH_CAPTURE_REPAIR_READMISSION.json`. It claimed only
`h100-paged-fp8-e00mkpyvykfak0bg1m` at `18:50:57Z`. Its first staging copy
found that the temporary directory lacked `input/`; no guest scientific marker
or candidate request existed. A durable replacement owner now loads the
unchanged hash-bound owner and creates only each destination parent before the
original delta-copy operation. It inherited the same pool claim and copied all
six bound repair-delta files; the original waiting owner was stopped only after
the replacement was live, heartbeating, and past the repaired copy boundary.

Evidence: `GRAPH_REPAIR_OWNER_TERMINAL.json` preserves the failed pre-science
SCP diagnostic. `REPAIR_PATCH_GRAPH_STAGE_INPUT.json` records that control and
component remain unreplayed and candidate submission remains false. The live
replacement is recorded in `STATUS.json.active_session` as PID `1987809`,
`GRAPH_REPAIR_OWNER_STATE_REPAIR2.json`, `unit_manager: pid`; its progress
reached repair-delta ordinal 6/6 and its heartbeat refreshed the original
`18:50:57Z` claim.

Interpretation: this is an ordinary staging-parent defect, not scientific
evidence or a consumed candidate sample. The retained checkpoint, image, and
one candidate authorization remain intact.

Next move: the durable owner verifies/promotes the delta, runs CUDA-graph
capture as discovery, then submits at most the sole candidate c32 request and
retrieves its terminal before the fixed release deadline.

## 2026-07-26 — replacement crossed CUDA-graph discovery boundary

Action: inspected only the local replacement-owner state, its preserved
generation-1 pre-submission diagnostic, and the owner retry entrypoint. The
replacement PID `1987809` remains live with the original claim timestamp and
a successful `18:54:55Z` heartbeat. Its durable progress is
`candidate_graph_capture_started` at `18:53:30Z` after all six repair-delta
rows copied.

Evidence: the only pending `REPAIR_READY.json` is generation 1, created by
the superseded PID `1986779`; its diagnostic proves the missing temporary
`input/` directory and contains no invocation marker. The active replacement
is already beyond that invalidated copy operation. No endpoint terminal is
present and no local evidence authorizes inferring candidate consumption.

Interpretation: issuing a request to the stopped generation would not resume
the active owner and would be stale coordination, not an in-place repair. The
correct disposition is to preserve the active owner and await its compact
terminal or a fresh repair generation from that owner.

Next move: the live owner completes CUDA-graph discovery, performs at most
the one admitted candidate request, retrieves its terminal, and releases only
on that terminal or the fixed deadline.

## 2026-07-26 — non-c32 CUDA-graph capture repair requested

Action: retrieved the compact failed attempt archive and found the server
reached CUDA-graph capture after identity/oracle validation but failed at the
capture scheduler's batch 30 (`q_shape=[360,32,256]`), before candidate
science start. Patched only `sitecustomize.py`: batch-32 target verification
still requires the packed exact path, while non-c32 graph-capture batches use
the original backend and are recorded as `graph_capture_passthrough` rather
than a candidate fallback. Regenerated the full/repair manifests and submitted
the hash-bound request for live repair generation `graph-repair-1-1785092154`.

Evidence: attempt-1’s `INVOCATION_STATE.json` has
`identity_validated=true`, `oracle_validated=true`,
`candidate_graph_capture_passed=false`, and
`candidate_science_started=false`; its route audit contains the sole rejected
batch-30 row. Eight focused consumer/graph-repair tests pass. The live owner
accepted the request, archived the prior zero-request root, retains the same
`18:50:57Z` claim, and crossed retry delta-copy ordinal 5/6.

Interpretation: the failure is a CUDA-graph batch-geometry integration defect,
not a kernel or endpoint measurement. Control and component remain preserved;
the candidate arm remains unconsumed.

Next move: owner finishes staging the narrow patch, repeats CUDA-graph
discovery, and only then issues the sole c32 candidate request.

## 2026-07-26 — immutable endpoint semantic localization terminal

Question: did the consumed candidate fail token gates because of request
joining, observation/result construction, emission, or upstream candidate
computation?

Action: streamed only the immutable attempt-2 archive members and joined each
candidate response to token events by its unique SSE RID, then joined candidate
to control by the 32 durable request SHA-256 identities. Reconstructed all
scheduler token deltas in event order, checked every cumulative completion
counter, decoded them with the bound project-local tokenizer, and compared the
complete decoded stream with raw SSE text and the final tokenizer/parser event.
No GPU was claimed and no candidate, control, or component arm was replayed.

Evidence: `SEMANTIC_LOCALIZATION_RESULT.json`
(`sha256:7e59aab982b1f6c833a444d4635c1347db6995cfdcb749902d556eb57ab8a46b`)
binds the archive, endpoint terminal, oracle, tokenizer, observer, consumer,
and packed endpoint sources. Fifteen requests are token-exact; 17 diverge and
12 of those diverge at token zero. Across all 32 candidate requests, 1,272
scheduler events have exact cumulative counters, all 32 final scheduler
deltas equal tokenizer-emitted IDs, all final parser bytes decode exactly, and
all complete SSE text equals the accumulated token decode. Every affected
request therefore has a null first target-to-emitted inconsistency. The
terminal spend is conservatively settled at `$2.716333`; offline localization
added no provider exposure.

Interpretation: this is a genuine candidate-path computation divergence before
detokenization, not an observer, identity join, serialization/result
construction, or server-emission defect. The valid 3.6504% timing reduction
remains useful physical evidence, but the exact endpoint is semantic-unsafe
and cannot promote. The original reject terminal is reproduced offline, so no
corrected decision terminal is warranted.

Next move: director consumes the localization terminal and closes this exact
endpoint candidate. The smallest materially different future discriminator is
a newly admitted non-replay capture of native-versus-packed logits, top-2
token IDs/margins, and attention output at the first target-verification step
for the earliest divergent request.

## 2026-07-26 — FP32 partition redesign closed by global HBM bound

Question: can a materially new partitioned reduction retain at least 80% of
the measured V2 time saved while cutting its numerical error by an order of
magnitude?

Action: implemented `packed_m384_attention_fp32_partitioned.py` against the
real page-size-one FP8 paged-KV/extend producer and unchanged output boundary.
It persists scores, max/sum state, and per-partition numerators in FP32; value
CTAs own one 512-token partition and a 16x32 tile, followed by an FP32
rescaled merge. Added a lifecycle-pure, new-candidate-only component runner,
but did not admit or execute it. Ran a deterministic CPU proxy over exact
D256/P1024 and D512/P4214 geometry, including all 12 rows for four
representative heads, shuffled pages, the 118-token global tail, masks, padded
score strides, and an extreme-Q fixture. No GPU was claimed and no V2
component or endpoint arm replayed.

Evidence: the sampled FP64 proxy reports redesign relative L2 of `0.001671`
local and `0.001668` global, respectively 16.1x and 17.4x below the measured
V2 errors; max error improves by more than 300x. The stock partitioned-FP32
A/A proxy envelope is about `3.1e-7`. However, exact compulsory traffic adds
397,934,592 bytes local and 3,081,388,032 bytes global over V2. Even at the
inventory H100's unattainable 3.35 TB/s peak, the global lower bound is
`0.9198 ms`, 12.77x the `0.07205 ms` admitted regression; the 50-local/
10-global lower bound is 1.56x its allowance. Five source, quantizer, runner,
and terminal tests pass.

Interpretation: accuracy recovery is plausible, but this exact FP32
score-workspace plus partition-numerator representation is physically closed.
Compiler resource measurements cannot reverse a failed compulsory-byte lower
bound. Complete 32-head H100 correctness, actual stock A/A, and endpoint
target-logit margins also remain unavailable, so no READY artifact is honest.
`PACKED_M384_ACCURACY_REDESIGN_RESULT.json` is the scientific terminal and
adds `$0` provider exposure.

Next move: close this representation. Any new lineage must eliminate global
score rereads and the numerator HBM round trip before compiler/GPU admission,
and bind a newly admitted target-logit margin oracle.

## 2026-07-26 — on-chip streaming cluster clears offline gates

Question: can exact FP32 online-softmax/value state remain on chip while
removing both HBM intermediates that closed the prior representation?

Action: implemented `packed_m384_streaming_cluster.cu`. One 256-thread CTA
owns each local sequence/head. Global uses a portable two-CTA SM90 cluster:
rank 0 stages shuffled page-size-one FP8 K, produces FP32 probabilities, and
hands them to rank 1 through distributed shared memory; both ranks stage one
D256 V slice and retain twelve FP32 output accumulators per thread. No scores
or partition numerators are persisted to HBM. Added a lifecycle-pure future
component runner with fresh stock A/A, complete FP64 consumption, graph
replay, alternating timing, and cuobjdump resource gates. No GPU was claimed
and V2 was not invoked.

Evidence: the deterministic complete CPU experiment consumes every output for
32 sequences, 32 heads, 12 rows, and D256/D512—9,437,184 elements. Relative
L2 is `0.00165822` local and `0.00165914` global, improving measured V2 by
16.24x and 17.48x; max error improves by 304x and 312x. Full-row versus
64-token online FP32 A/A relative L2 is below `4.45e-7`. The global design is
SM90-legal at cluster size 2 and 64,656 dynamic-shared bytes/CTA, with twelve
source-visible FP32 accumulators/thread. Its conservative 214,106,112-byte DSM
handoff floor is `0.06391 ms`, inside the `0.07205 ms` incremental allowance.
Global and 50-local/10-global roofline floors are `1.657 ms` and `26.636 ms`,
inside `2.982 ms` and `63.419 ms` ceilings. Twelve focused tests pass.

Interpretation: all director-defined offline READY gates pass. This is an
admission result, not an accelerator measurement or endpoint-safety claim.
The decisive future falsifier is an SM90 compile/run: at most 64
registers/thread, zero stack/local-memory traffic, exact GPU error within the
bound gates, and warm p50 no slower than `0.67194 ms` local / `2.98216 ms`
global.

Next move: director may admit one new stock-versus-streaming H100 component
measurement using the hash-bound lifecycle-pure runner. Repair ordinary
compile/API defects in the retained session; never replay V2 or promote before
the new component terminal.

## 2026-07-26 — cold-H100 streaming component owner bound

Question: can the director safely admit the one new streaming stock-versus-
candidate H100 component cycle without reusing the retired V2 lifecycle?

Action: added `run_streaming_h100_component_owner.py` and the immutable
`STREAMING_H100_COMPONENT_INPUT_MANIFEST.json`. The owner verifies the
admission, a future readmission's exact `$7` reservation, H100 claim, deadline,
runner/source hashes, and SSH identity; it then reconciles a content-addressed
remote packet, pulls the pinned image, invokes the exact lifecycle-pure runner,
retrieves compact raw artifacts, and releases only after a typed scientific
terminal. Pre-science staging, launcher, compile, runtime-API, and retrieval
failures retain the claim with a repair handshake.

Evidence: `PACKED_M384_STREAMING_H100_COMPONENT_READY.json`
(`sha256:14d179bf4c065d7aefe3f3d73f60caf3f30a1939a630ba89401b8b5374964d68`)
binds the owner (`7ac55b0a3ac3f8ec6035b32f9a8902ddb011dcdd0197141f852cc2870aec02f4`),
the four-file packet manifest (`5189f2beab6cd7def9fa6d7ee3a1e8297c5076f6a533b949814246f8ad595583`),
and the admitted streaming-ready predecessor. Local `py_compile` and static
contract checks pass; `manifest-pack` produced the five-member packet with
SHA-256 `917eee09ef74f7e38bb7ea8c1844aa0c396641e4db936f5353f09f56e0f62b9b`.
The pre-existing numpy-based offline test cannot import `numpy` on this
coordinator; no GPU attempt occurred.

Interpretation: this is executable launch preparation, not a measurement. The
project remains provider- and GPU-ineligible, has no active session, retains
`actual_spend_usd: 2.716333`, and has consumed no new candidate sample.

Next move: director records the exact $7 reservation, consumes READY, and
issues a bench/deadline readmission. The researcher then atomically claims the
named H100 and launches this owner through `detached-owner --unit-manager pid`.

## 2026-07-26 — retained-owner repair loop corrected

Question: can a recoverable H100 component failure resume under one continuous
claim without replaying an ambiguous CUDA submission?

Action: replaced READY generation 1 atomically with generation 2 and amended
the same owner. Every repair generation now waits for, hash-verifies, records,
and consumes `REPAIR_REQUEST.json` before resuming only its permitted stage.
Pre-science states may restage, retry the unsubmitted component, or retrieve;
`science_started` and terminal-marker states permit retrieval or an explicitly
hash-recorded offline result-construction patch only. The owner loops through
fresh nanosecond repair IDs while the heartbeat remains live and only releases
after a scientific terminal.

Evidence: generation 2 READY is
`23ad5ea6b5a7e2dd42b26fa39358566aefe19bf72f316df77596e09eb27de749`,
binding owner `c4fdbba4d6a860c07e63f6b92738f733d2c3f8249b34d2bb8c274016c2944efc`
and the director repair binding. A local execution of the shared handshake
created a ready/request pair, exercised owner request consumption, and proved
that `REPAIR_APPLIED.json` is written; its invocation gate allows retry for
`pre_science` but denies component replay for `science_started`.

Interpretation: the prior failure was an owner-control defect, not scientific
evidence. No H100 was created or claimed, no CUDA work ran, and actual spend
remains `$2.716333`.

Next move: director consumes generation 2 and supplies the H100 readmission.

## 2026-07-26 — registered H100 blocked by cumulative spend cap

Question: may the project claim the director-registered two-hour H100 lifecycle
under the restored cumulative `$7.00` reservation?

Action: reconciled the current status spend with the registered H100's fixed
provider-start-to-cleanup interval before the atomic claim. No owner, SSH,
container, CUDA, V2, or endpoint operation was started.

Evidence: `STATUS.json` records prior `actual_spend_usd: 2.716333`, leaving
`$4.283667` of the explicit cumulative `$7.00` cap. The registered H100 rate
is `$2.9597222/hour` and its fixed lifecycle is 7,200 seconds, for
`$5.9194444` exposure. The resulting minimum project exposure is `$8.6357774`,
which exceeds the authorized ceiling by `$1.6357774`.

Interpretation: this is a typed external budget boundary, not an experiment or
scientific result. Claiming would violate the user's cumulative-spend rule even
though the readmission and resource are otherwise technically ready.

Next move: director must increase the cumulative reservation or explicitly
reassign a smaller verified lifecycle exposure; only then claim the named H100
and launch the exact detached owner.

## 2026-07-26 — retained H100 pre-science compiler repair

Question: can the admitted streaming component reach its sole exact consumer
without changing its hash-bound runner or CUDA source?

Action: preserved the live owner, claim, packet, and image. Archived each
zero-request pre-science output root with SHA-256 manifests, then submitted
hash-recorded `run_unsubmitted_cycle` requests. The final repair patches only
the generated, root-owned Ninja `cuda_cflags` with the pinned image's bundled
NVIDIA development-header roots; it does not alter the frozen runner, source,
control, or component contract.

Evidence: the first missing `cusparse.h` and then `cublas_v2.h` diagnostics
were both pre-science (`INVOCATION_STATE.json` records no candidate CUDA
submission). The final repair helper emitted `patched .../build/build.ninja`,
and owner state advanced to `launch_attempted` at `21:31:12Z`. PID `2081506`
remains live with matching start ticks and the pool heartbeat is non-stale.

Interpretation: no scientific sample has been consumed; the owner is now
executing the one admitted component cycle under its original deadline.

Next move: let the durable owner retrieve a typed terminal or expose another
bounded repair handshake; do not poll or replay V2/endpoint work.

## 2026-07-26 — CUDA math-constants retained repair

Question: can the same pre-science component compile progress without changing
the admitted CUDA source or runner?

Action: retrieved the failed compile output once, archived its zero-request
root and hash manifest, then submitted a hash-bound `run_unsubmitted_cycle`
request. The repair adds only `-include /usr/local/cuda/include/math_constants.h`
to the generated Ninja CUDA flags alongside the already-required pinned-image
development headers.

Evidence: the prior invocation remained `pre_science` with no candidate CUDA
submission; its sole compiler error was `CUDART_INF_F` undefined. The pinned
image contains `math_constants.h` and defines `CUDART_INF_F`. The repair helper
recorded `patched .../build/build.ninja`; live owner state crossed back to
`launch_attempted` at `21:35:12Z`, with a non-stale pool claim.

Interpretation: the component cycle remains unconsumed and is executing under
the original controller, claim timestamp, budget, and deadline.

Next move: await the owner terminal or a subsequent bounded repair request;
do not replay V2 or run endpoint work.

## 2026-07-26 — CUDA 12.9 cluster-launch compatibility repair

Question: can the hash-bound CUDA source compile against the pinned image's
newer anonymous `cudaLaunchAttributeValue::clusterDim` ABI without altering
the scientific program?

Action: archived the unsubmitted compiler output with hashes and added a
compiler-only compatibility header to the generated Ninja flags. The header
rewrites `dim3(x,y,z)` as a braced initializer, which is valid both for the
ordinary launch dimensions and CUDA 12.9's anonymous cluster-dimension struct.

Evidence: the prior failure was pre-science and isolated to assignment of
`dim3` into `clusterDim`. An exact pinned-image `nvcc` compilation of the
unchanged source with the compatibility header succeeded. The hash-bound
repair request was consumed and owner state advanced to `launch_attempted` at
`21:38:29Z`.

Interpretation: this remains a same-claim integration continuation; no
candidate sample, V2 replay, or endpoint action has occurred.

Next move: let the durable owner finish the sole component cycle or expose a
new typed repair handoff.

## 2026-07-26 — fixture-dtype binding boundary

Question: did the compiled candidate consume a CUDA sample before the
fixture's index dtype failed?

Action: retrieved the raw stdout/stderr and compiled extension artifacts,
then used the owner's allowed offline-result-construction path to record a
hash-bound classifier repair. It atomically preserved the raw-log hashes and
reclassified the event as a host-side pre-science dtype guard; the owner then
opened fresh repair ID `streaming-h100-1785102152052403190` while retaining
the original claim and heartbeat.

Evidence: the extension compiled and loaded, but its `kv_indices` type guard
raised `packed_m384_streaming_int32_indices_required` before a kernel launch.
The manifest-bound fixture explicitly produces `pages` as `torch.int64`, while
the same manifest-bound CUDA source requires `at::kInt` and `int32_t*`.
`REPAIR_TERMINAL.json` records the raw stdout/stderr SHA-256 values.

Interpretation: no candidate CUDA sample was consumed despite the runner's
premature `science_started` marker. Mutating the fixture would change an
admitted manifest file, so it is a binding-rebind boundary rather than a safe
in-place replay.

Next move: director must bind the corrected int32 fixture and an updated
manifest/readmission; until then keep PID 2081506 and its warm claim retained
at the fresh repair handshake without requesting a component replay.

## 2026-07-26 — director-authorized fixture-dtype rebind

Question: can the unsubmitted component resume with the required int32 page
indices while preserving every scientific identity and the same warm owner?

Action: consumed `DIRECTOR_HOPPER_PACKED_STREAMING_FIXTURE_DTYPE_REPAIR_20260726T2146Z.json` and changed only the fixture's `torch.randperm` dtype from
int64 to int32. Regenerated the input manifest, recorded a repair-local rebind
packet, atomically replaced only those two verified members in the retained
remote packet, archived the zero-request output root, and requested only
`run_unsubmitted_cycle` under repair ID `streaming-h100-1785102152052403190`.

Evidence: corrected fixture SHA-256 is
`95e904aa1d196ec230d4be62c2e9a7bae83931f399592cd21a9adb978b7ef637`;
corrected manifest SHA-256 is
`618ce17579ca30632c11926e4f5738bffc90c4de30d316df800ff6decf2c320a`.
The request is hash-bound to the director repair plus unchanged candidate,
control, and runner identities. Owner state crossed `launch_attempted` at
`21:51:30Z` under the original PID and claim.

Interpretation: the binding defect is resolved and the sole component cycle is
in flight; no V2 or endpoint operation was requested.

Next move: consume the durable owner terminal or a future typed repair
diagnostic without replaying any completed scientific stage.

## 2026-07-26 — post-submission CUDA launch incompatibility

Question: did the corrected component produce an interpretable candidate row?

Action: retrieved the remote stdout/stderr, compiled extension and invocation
marker. The corrected fixture passed the int32 guard and the candidate was
submitted, but `torch.cuda.synchronize()` returned an unspecified CUDA launch
failure before a numerical or timing row persisted. Used the allowed offline
construction path only to persist `RUNTIME_INCOMPATIBILITY.json` and its raw
log hashes; no result terminal was synthesized and no replay was requested.

Evidence: `INVOCATION_STATE.json` records `candidate_cuda_invocation_started:
true`; the compiled shared object and resource report are present; stderr
records the CUDA launch failure. The incompatibility artifact hashes stdout as
`ab9d857927e8aee78e4aedf7408cbbb62cffc68fd5f548723cd6b61aa1d94117` and
stderr as `7a9837fae99c705420c782ea35fc3efb3125e3de3a5b9dc1c6e97c9673a51bff`.

Interpretation: this is not a valid positive/negative scientific component
measurement, but it is a post-submission runtime incompatibility and cannot
be replayed under the admitted contract. PID `2081506` remains live and
heartbeating under non-replay repair ID `streaming-h100-1785102961465033086`.

Next move: director must choose a source-level candidate repair or terminal
disposition; retain the warm claim and do not replay V2, endpoint, or this
component cycle.

## 2026-07-26 — deep offline launch-failure localization

Question: does the immutable launch packet identify a first invalid
source-level invariant without replaying CUDA?

Action: hash-bound the source, corrected fixture, runner, generated Ninja
configuration, compiled object/module, SM90a resource report, invocation
marker, incompatibility record, and raw logs. Derived every local/global
pointer bound and launch/shared-memory quantity offline, then used only the
owner's `offline_result_construction` path to persist the typed localization
terminal.

Evidence: all frozen local d256 bounds are in range; its 1,024-CTA grid is
cluster-size-1 divisible and uses 42,128 dynamic plus 1,024 compiled static
shared bytes, 96 registers/thread, and zero stack bytes. The runner, however,
records `science_started` before two stock calls and the candidate call and
has only one synchronization afterward. The unspecified asynchronous error
therefore has neither arm identity nor a device fault PC. Terminal
`cbebfdcc5e7c95342bd5619031dce5bf0cac025568c5593bc6aa1813e4369033`
records
`preserved_evidence_insufficient_for_unique_source_level_fault_localization`;
no CUDA, component replay, V2 replay, or endpoint action occurred.

Interpretation: the local candidate is suspect by execution order, but naming
a defective source line would exceed the preserved evidence. This remains an
uninterpretable invalid attempt, not a performance or correctness result.

Next move: PID `2081506` retains the original claim under fresh repair ID
`streaming-h100-1785103561963304790`. Director must either bind a later
arm-isolated discriminator or issue terminal release disposition before
`2026-07-26T22:59:10Z`; no replay is currently authorized.

## 2026-07-26 — arm-isolated discriminator launched

Action: the retained owner constructed the required offline invalid-attempt
terminal and released. A fresh H100 claim at `22:17:31Z` then launched the
director-bound arm-isolated controller. Two pre-science staging defects
(missing remote parent and then missing build directory) were preserved in
the owner logs and repaired in place; neither reached CUDA. The fourth owner
generation is live with the corrected CUDA development-header and CUDA-12.9
cluster-dimension compatibility inputs hash-bound in its packet.

Evidence: detached PID `2137024` (start ticks `122058439`) crossed
`runner_launch_attempted` at `22:22:49Z` against the fresh packet digest
`6d4507f3c9a6ede3431a3bbddb3195ab47c31709c319142ea73e57bd3ed30223`.
No per-arm completion marker exists yet, so no stock or candidate result has
been interpreted or replayed.

Next move: allow this owner to persist the first per-arm completion/fault or
the bound terminal, retrieve it, and release by the absolute deadline.

## 2026-07-26 — arm-isolated terminal

Action: reconciled the detached owner terminal and preserved the supervisor
drain-after-release fence. No candidate, V2, or endpoint replay was issued.

Evidence: local d256 stock A, stock B, and candidate all completed at separate
synchronization boundaries; its stock A/A delta was zero and the candidate
reached the FP64 consumer (`relative_l2=0.00165834`) plus the bound 25-rep
timing (candidate p50 `17.2093 ms`, control p50 `1.48038 ms`). Global d512
stock A and B also completed independently, but the candidate's own marker
records `cudaErrorLaunchFailure`. The terminal is
`artifacts/streaming-h100-arm-isolated-20260726t2210z/PACKED_M384_STREAMING_ARM_ISOLATED_RESULT.json`
(`c63c5ce8…`). Full registered provider exposure from `20:59:09Z` through
release at `22:25:14Z` is `$4.245923`.

Interpretation: this isolates the unspecified launch failure to the unchanged
global d512 candidate rather than either stock arm. The local timing is not a
promotion result because the exact global geometry fails; the admitted one
shot is consumed and the project must not replay it.

Next move: await director disposition with the drained bench and immutable
terminal preserved.
