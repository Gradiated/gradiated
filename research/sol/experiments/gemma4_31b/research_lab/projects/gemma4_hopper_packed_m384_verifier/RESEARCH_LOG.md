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
