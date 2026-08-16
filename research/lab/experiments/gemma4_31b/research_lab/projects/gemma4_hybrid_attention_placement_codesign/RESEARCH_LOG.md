# Research log

## 2026-07-26 — repaired NGRAM target-runtime readmission in progress

Question: can the unconsumed full-model dual-cache component reach the pinned
NGRAM target-verify consumer on the retained H200 without changing the
scientific binding?

Action: atomically claimed `h200-dflash-adapter-e00vyqp7gxsr34wrtz` at
01:58:40Z and launched one resident target server under a PID-backed durable
controller. The first launch was pre-science: its raw server log proves that
the live pinned image has no `eagle_worker.NGramWorker`. A direct image query
found `sglang.srt.speculative.ngram_worker.NGRAMWorker` instead. The narrow
same-claim import/class-name repair is hash-bound through the repair handshake
at `24a959d3337c7913bbc9d76f6f93477413d74d3f6469a8756674b90ff0d8fead`;
all five local dual-cache behavioral tests pass. Replacement controller PID
1458909 started at 02:05:14Z and is loading the same single target model.

Interpretation: no target-verify request, component comparator, or endpoint
sample has been consumed. The first failure is an ordinary pinned-runtime
symbol mismatch, not evidence against the cache-placement hypothesis. The
next move is to retain the claim through the replacement's live attachment and
run only the full-model component; exact-c32 remains prohibited until all
component gates pass.

## 2026-07-25 — source-complete 55-local/5-global candidate

Question: can changing the pinned 60-layer 5-local/1-global geometry produce a
material H200 c32 gain with a credible recovery path?

Action: verified the three director-bound hashes, the exact M384 trace, the
scope-matched prefill subtype map, the prefill profile, and the four-row NCU
export. `simulate_placements.py` reconstructs all 60 layers. For verification
it maps 15 exact c32 target cycles into each layer's QKV, attention, output,
gate/up, and down cost. For prefill it combines measured local/global attention
subtype time with measured aggregate FP8-linear time apportioned by exact
projection FLOPs. It also computes exact causal/windowed attention pairs, FP8
KV bytes, projection parameters, and two counter-derived full-request pass
counts.

Evidence: stock M384 attention is `1.339264 ms` per local layer and
`3.275520 ms` per global layer; the valid mixed component is `0.936512 ms`
local and `3.274080 ms` global. The trace-derived attention projection medians
are `0.138144 ms` local and `0.211249 ms` global. Scope-matched prefill
attention is `34.671859 ms` per local layer and `150.025741 ms` per global
layer per c32 batch. Placement-only movement with ten global layers has zero
modeled cost effect.

Result: retain one quality-unsafe candidate with full layers
`[5,17,29,41,53]`. Replacing the other five global layers predicts
`12.053363 ms` less target-cycle work, `31.526–33.291 ms/request` total
savings, and `0.591858–0.593624 s/request` against the locked
`0.625149102` denominator: `5.043–5.325%`. It removes `330,301,440`
attention-linear parameters and `1,419,509,760` c32 KV bytes (`7.493%`).
Measured NCU geometry per converted layer moves from 255 to 173
registers/thread, 102.4 to 37.888 KiB dynamic shared memory, 7.76 to 15.52
waves/SM, 1.351311 to 0.662617 GB DRAM reads, and 6.713353 to 1.554938 GB L2
bytes. No batching gain is credited because prior c48/c64 results were
negative.

Interpretation: this is a source-complete performance candidate, not a
deployable model or a measured endpoint. The M8 endpoint consumer produced no
durable pair, and prefill linear time is a FLOP-calibrated allocation rather
than a per-shape timing. The cheapest later proxy copies nearest-local
attention weights into the five converted modules, keeps MLP/norm weights,
and measures one exact c32 target-forward comparison before any endpoint.
Recovery requires teacher hidden-state/attention/logit distillation on
long-context and tool-use data, then exact GPQA-Diamond, TauBench,
long-context, tool-format, and multimodal gates.

One initial local invocation was invalid only because the NCU CSV units row
was parsed as a sample. The consumer now filters nonnumeric IDs; the same
deterministic simulation completed without changing the scientific question.
`python3 -m unittest -v test_simulate_placements.py` passes both binding and
combinatoric tests. No GPU was claimed and provider spend is `$0`.

## 2026-07-25 — conditional H200 component not run

Question: can the promoted 55-local/5-global proxy be measured through one
exact-c32 target-forward control/candidate component on the retained H200?

Action: audited `DIRECTOR_HYBRID_55L5G_H200_COMPONENT_BINDING.json` and all
five bound input hashes. Every hash matched, including the binding digest.
The required predecessor `DFLASH_CYCLE_ORACLE_TERMINAL.json` was absent and
the predecessor project remained active with the H200 claimed, so the claim
gate was closed at 2026-07-25T18:05:01Z. No bench was claimed, no checkpoint
was altered, and no runtime, profiler, endpoint, training, or quality arm
started. The project-local tree has no exact-runtime proxy/consumer to run
offline; adding a speculative runner after the closed gate would not create
decision-bearing evidence.

Result: persist `HYBRID_55L5G_H200_COMPONENT_TERMINAL.json` as typed
`unrun_claim_gate_closed` with zero incremental spend and yield the warm bench
window to grouped LM-head. The offline result remains source-complete only:
predicted 5.043–5.325% service reduction and 7.493% c32 KV residency saving;
no H200 component claim is made.
## 2026-07-25 — measured hybrid component

The repaired launch window was claimed atomically on `h200-dflash-adapter-e00vyqp7gxsr34wrtz` at 20:14:32Z. The five bound inputs were copied into `inputs/bound/` and hash-verified. A five-layer nearest-compatible-local weight-copy proxy (candidate layers 5,17,29,41,53; copied local layers 11,23,35,47,59; MLP/norm/embedding/lm_head preserved) was measured once through pinned SGLang v0.5.13 with profiler off, exact c32, and no endpoint/training/DFlash replay.

Measured result: weighted attention reduction `0.20334496337472074` (split checks `0.2033000292246645`, `0.20262042704666094`); local sliding component median 1.34915 ms control vs 0.94061 ms candidate; full component median 3.29338 ms control vs 3.29469 ms candidate. Both outputs were finite and allclose; full output was bit-exact and candidate replay was bitwise reproducible. This is component evidence only, not a quality or deployability result. The H200 was released ready at about 20:18Z; conservative project spend recorded as $0.19.

## 2026-07-25 — endpoint claim gate closed

Question: can the settled quality-unsafe 55-local/5-global proxy be tested as one exact-c32 stock-control/candidate endpoint pair?

Action: verified `DIRECTOR_HYBRID_55L5G_H200_ENDPOINT_BINDING.json` and its binding hash. The hard claim deadline was `20:30:00Z`; the gate and clean shared-pool state were checked at `20:30:35Z`. The retained H200 was available with a `22:00:00Z` lifecycle deadline, but the binding explicitly forbade a late claim. No GPU was claimed, no endpoint or request invocation started, no DFlash or component work was replayed, and no new spend accrued.

Result: persist `HYBRID_55L5G_H200_ENDPOINT_TERMINAL.json` as typed `unrun_claim_gate_closed`. The endpoint hypothesis remains unmeasured; the prior component result remains settled component-only evidence. Await a new in-window director binding rather than violating the expired contract.

## 2026-07-25 — phase-selective dispatcher and dual-cache bound

Question: can the five measured local proxies run only in speculative target
verification while prefill and ordinary decode remain on stock attention?

Action: traced the pinned `ForwardMode`, ngram verifier, CUDA-graph runner,
Gemma attention constructor, SWA/full cache pools, and Triton cache writes.
`TARGET_VERIFY` is one scalar mode for the whole captured graph and owns
request-major `batch × draft_depth` rows (`32 × 12 = 384` here); padding rows
own no request. Verification allocates all draft KV slots, then frees or moves
unaccepted rows. Gemma's global and local modules cannot share K/V: they have
different head dimensions (`512` versus `256`), KV-head counts (`4` versus
`16`), RoPE, projection shapes, receptive fields, and cache layouts.

Result: `phase_dispatcher.py` is an executable, source-bound dispatch contract.
At converted layers `[11,23,35,47,59]`, prefill/decode use stock attention and
also write proxy-local shadow K/V; `TARGET_VERIFY` uses proxy-local attention
and also writes stock-global shadow K/V. Allocation, accepted-row moves, and
rejected-row frees must be mirrored across both banks. The phase branch is
capture-static because the speculative graph is captured separately as
`TARGET_VERIFY`; only values and logical row counts vary at replay.

Cost: the measured placement model supplies `12.548–14.313 ms/request` gross
target-only savings. Width-scaled versus full-QKV-launch bounds for the shadow
projections, plus analytical H200 peak-bandwidth write floors, cost
`0.755–1.904 ms/request` when ordinary-decode steps are zero. Net is therefore
`10.644–13.558 ms/request`, or `1.703–2.169%` of the locked
`0.625149102 s/request` denominator, with `1,342,177,280` extra c32 cache bytes
(`7.085%`). A 358-step ordinary-decode sensitivity remains positive at
`5.897–11.183 ms/request`, but that is a scenario, not measured workload
telemetry.

Decision: retain a narrow `source_complete_candidate` for one later exact-c32
component falsification, not an endpoint. The first expected semantic
divergence is the layer-11 target-verification attention output. The later
component must populate both banks, prove stock equivalence before verification,
replay one 384-row verify graph, mirror an accept/move/free pattern, prove the
next stock-operator decode matches an eager dual-cache reference, and show
positive net timing. Stock operators after verification do not restore
all-stock semantics: later-layer stock K/V for accepted rows are derived from
hybrid hidden state after the first converted layer diverges. No GPU was
claimed, no endpoint ran, no provider mutation occurred, and incremental spend
was `$0`. `python3 -m unittest -v test_phase_dispatcher.py` passes 8 tests.

## 2026-07-25 — retained-H200 adapter attempt closed

Question: does the bound phase-selective dual-cache design pass the one exact
H200 component gate?

Action: claimed the retained H200 at 21:16:17Z, repaired two pre-science
launcher defects in place (guest-host Python then a packet syntax error), and
ran the pinned SGLang attention operator under the retained container. The
worker persisted its invocation marker, raw logs, a 384-row cache ledger, and
CUDA-event timings before the bench was released ready at 21:21:25Z.

Evidence: the narrow adapter recorded finite stock/proxy outputs, exact
384-row ownership, identical stock/proxy allocation/write/move/free ledgers,
bitwise CUDA-graph replay, and a synthetic `1.9460 ms` median net timing.
However, it invoked only the attention operator with synthetic KV tensors; it
did not execute pinned Gemma stock prefill/ordinary decode or the post-accept
stock full-model eager reference required by the binding.

Interpretation: classify `infrastructure_terminal`, not an exact positive
component result. The synthetic timing cannot be used for campaign economics
or a phase-dispatch claim. Conservative cumulative project exposure is
`$0.399` (`$0.19` prior plus about 307 seconds of this H200 claim at
`$2.45/hour`). No endpoint, training, model server, or provider lifecycle
operation ran.

## 2026-07-25 — full-model repair owner launched

Question: can the admitted phase-selective dual-cache mechanism be exercised
through the pinned full Gemma producer rather than the settled synthetic
attention adapter?

Action: atomically claimed the retained H200 at 21:35Z and verified that the
pinned image exports `Gemma4ForCausalLM`, `ModelRunner`, and the production
`ForwardBatch` contract. The first durable owner attempted to materialize the
project-local immutable checkpoint snapshot using hardlinks. The remote
filesystem rejected that link with `Operation not permitted`; this was a
pre-science staging defect, and no candidate CUDA or scientific sample began.
The claim was retained, the raw diagnostic was preserved, and the same owner
was amended to copy-on-write-or-copy each immutable file into a new
project-local remote snapshot before the full-model invocation.

State: retry owner `PHASE_SELECTIVE_FULL_MODEL_OWNER_UNIT_RETRY.json` is live
under the existing claim and has made forward staging progress (37 GiB of the
snapshot at the first grouped observation). It will run the full-model
constructor immediately after atomic snapshot finalization; no component or
endpoint result has been recorded yet.

## 2026-07-26 — single-model memory and adapter recovery

Question: can the stranded pre-science full-model OOM be repaired without
reclaiming the H200 or changing the still-unconsumed component question?

Action: replaced the standalone `ModelRunner` future-worker bridge with a
single-resident-model bridge and bound the exact production SGLang
`launch_server` construction used by the same target checkpoint on this H200.
The bridge attaches phase metadata only to the existing Gemma attention modules
at converted layers `[11, 23, 35, 47, 59]`; it rejects a second attachment and
does not allocate a model, tensor, or cache. The source-bound adapter retains
stock/proxy-local banks, the `32 × 12 = 384` target-verify ownership contract,
padded-row no-write policy, and mirrored alloc/write/move/free requirement.

Evidence: the exact target production server was previously measured at
`121,960 MiB` GPU residency. Adding the settled `1.25 GiB` shadow KV bound and
a deliberately conservative `10.5 GiB` graph/adapter/allocator reserve gives
an inferred `130.8515625 GiB` expected peak and `8.9484375 GiB` margin on the
`139.8 GiB` H200, satisfying the director's <=132 GiB and >=7.8 GiB gates.
`python3 -m unittest -v test_full_model_memory_adapter.py
test_phase_dispatcher.py test_simulate_placements.py` passes all 12 tests.

Result: `FULL_MODEL_MEMORY_ADAPTER_READY_TERMINAL.json` is the required
`source_complete_operational_repair` terminal (SHA256
`3a02677fbc0cc0b1a486927747191e4b68d80b13b400d3751b9c87566cb5d363`).
No GPU was claimed, no remote worker was started, no candidate CUDA or
scientific component ran, and cumulative project provider exposure remains
`$0.399`. The later director must re-admit the project after the certified-lazy
and FP8 queue; it alone may authorize the next H200 retry.

## 2026-07-26 — queue state and immutable recovery recheck

Question: has the prescribed queue boundary changed so that this project may
resume the deferred H200 component?

Action: verified the four bound JSON hashes, the three changed executable
inputs, and the narrow offline test suite. Read the named certified-lazy and
FP8 project statuses once against the current director decision; made no GPU
pool call and no provider mutation.

Evidence: `full_model_memory_adapter.py`, `phase_dispatcher.py`, and
`phase_selective_full_model_remote.py` still hash to the values recorded in
`FULL_MODEL_MEMORY_ADAPTER_READY_TERMINAL.json`. All 12 focused tests pass.
Certified-lazy remains active but requires its project-local c32 capture;
FP8 weight streaming is active at priority 8530 and is the director-admitted
next H200 component. The recovery terminal remains source-complete with a
derived 130.8515625 GiB peak and 8.9484375 GiB margin; its component remains
unconsumed.

Interpretation: the queue boundary is still in force. This project must not
claim the H200 or replay the OOM path. Keep the verified single-model
`launch_server` adapter frozen for a later director re-admission; cumulative
project exposure remains `$0.399`.

## 2026-07-26 — readmitted H200 single-model execution in progress

Question: can the admitted phase-selective adapter now enter the bound
full-model component path without the prior duplicate-`ModelRunner` OOM?

Action: claimed `h200-dflash-adapter-e00vyqp7gxsr34wrtz` at 00:29:34Z and
launched a durable controller. The first launch failed before model load
because the project-local checkpoint symlink escaped the container mount; the
second encountered only the stale exited container name. Both diagnostics and
`science_started=false` marker were preserved. The same claim now runs the
one-model SGLang `launch_server` construction with the immutable checkpoint
mounted directly at `/models/target` and the adapter attached at model load.

Evidence: at the first grouped post-repair snapshot the controller was live,
the container had been up 38 seconds, and H200 memory was 61,732 MiB. No
TARGET_VERIFY request, candidate CUDA submission, component terminal, or
endpoint pair has yet occurred. The controller retains the claim through its
01:15Z deadline and will expose an in-place repair boundary if the production
ForwardBatch driver remains incomplete.

## 2026-07-26 — production ForwardBatch dual-cache hook boundary

Question: can the already-resident pinned SGLang process execute the missing
TARGET_VERIFY dual-cache driver without restarting the healthy model?

Action: added `forward_batch_dual_cache_driver.py`, an in-process
`ModelRunner.forward(ForwardBatch)` hook that validates the pinned
`TARGET_VERIFY` mode, requires exactly 384 logical rows and one cache slot per
logical row, and records the mirrored stock/proxy cache obligation. Extended
the launch-time `sitecustomize.py` bridge to install that hook immediately
after the existing adapter binding. A new durable PID-owned controller then
performed exactly one strict resident health check and one execution-image
ForwardBatch import probe while keeping the original claim heartbeating.

Evidence: the healthy container reports `true` and the persisted attach proof
reports the five converted layers (`health.stdout.log`, SHA256
`d11b6df9ff227d6808478184b08697664fbbcfe0d9b0b6e481ae9f14c4fbe1ce`).
The pinned image imports the real `ForwardBatch` and `TARGET_VERIFY` enum
(`probe.stdout.log`, SHA256
`b64f254350aeb74c8f29f031640367fa81015ecc1142eb9894e4780cefbf21e5`).
Because that process was launched before the hook existed, it has adapter
metadata but cannot acquire the required in-process `ModelRunner.forward`
wrapper without replacing the healthy server. The probe did not submit a
TARGET_VERIFY batch: `science_started=false`, candidate CUDA=false, and no
component or endpoint sample was consumed.

Interpretation and next move: this is a recoverable integration boundary, not
a semantic or performance result. `REPAIR_READY.json` is hash-bound through
01:15Z (SHA256
`d72c74ab2751db8c14305a706227d540cebe1e07acdc8101410dcb22b566a9ad`);
the owner preserves the warm claim and server while awaiting a
director-authorized replacement-server request. The conditional endpoint pair
is deliberately unstarted.

## 2026-07-26 — preload replacement passed; NGRAM activation invalid

Question: can the repaired resident server reach the real production
`ModelRunner.forward(ForwardBatch)` target-verification boundary?

Action: replaced only the resident server under the retained claim, preserving
the image and checkpoint. The new process loaded the hash-bound
`sitecustomize.py` and `forward_batch_dual_cache_driver.py`, with native NGRAM
configured for depth 12. A bounded concurrent c32 activation then submitted
the exact 4,214-token request geometry.

Evidence: `FORWARD_BATCH_REPLACEMENT_OWNER_STATE.json` proves one resident
target model, converted layers `[11,23,35,47,59]`, and an installed in-process
`ModelRunner.forward(ForwardBatch)` wrapper. The activation returned 32 HTTP
500s, left the hook at `science_started=false`, and the server exited. The raw
server log is `artifacts/forward-batch-activation-20260726t0058z/server-raw.log`
(SHA256 `af7bd320edbca4a50827da28584dcb3b3f21d7d6d4984c35455044ab5c720451`).

Interpretation: no TARGET_VERIFY observation, cache lifecycle record,
full-model comparator, or endpoint sample persisted, so this is an invalid
infrastructure attempt rather than phase-placement evidence. The project also
still lacks executable proxy-local/stock-shadow KV operations; the next retry
must repair that implementation and the NGRAM process failure before it can
consume the component gate. Conservative cumulative exposure is `$1.61`.

## 2026-07-26 — NGRAM dual-cache consumer implemented offline

Question: can the concrete NGRAM `int(None)` failure be repaired while making
proxy-local and stock-shadow KV lifecycle real through the first target
verification consumer?

Action: replaced the observation-only `ModelRunner.forward` hook with
production-symbol adapters for `NgramVerifyInput.prepare_for_verify`,
`NGramWorker.forward_batch_generation`, `NgramVerifyInput.verify/_free_cache`,
and converted-layer `RadixAttention.forward`. The adapter allocates a distinct
proxy slot vector from the resident allocator, uses it as target-verify
primary, calls `set_kv_buffer` for the stock shadow, preserves accepted proxy
slots, and frees rejected proxy slots. Ordinary modes remain stock-primary
with a proxy shadow. No bench, SSH, remote process, or paid request was used.

Evidence: 15 focused tests passed, including the `None` geometry, 384-row
target allocation, first target-consumer path, target proxy/stock shadow,
ordinary stock/proxy shadow, accepted reuse, rejected release, and source
bindings. `python3 tools/devex/check.py` passed. Terminal:
`HYBRID_NGRAM_DUAL_CACHE_OFFLINE_IMPLEMENTATION_TERMINAL.json`.

Interpretation: this is source-complete consumer implementation, not a
measurement or quality result; the component remains unconsumed and cumulative
provider exposure remains `$1.61`. Pause for the DFlash terminal, released
bench, and fresh director admission before the exact runtime consumer run.
# 2026-07-26 — admitted target-runtime launch: typed import infrastructure terminal

Claimed `h200-dflash-adapter-e00vyqp7gxsr34wrtz` at 01:48:47Z under
`DIRECTOR_HYBRID_NGRAM_TARGET_RUNTIME_ADMISSION_20260726.json`, with a
durable controller and project-local source manifest. The single pinned Gemma
model loaded successfully (59.61 GiB reported after weights), but the launch
failed before adapter attachment or any candidate CUDA call: the pinned
runtime's `sglang.srt.speculative.ngram_worker` does not export `NGramWorker`.
The raw server log is content-addressed in
`artifacts/ngram-target-runtime-20260726t0149z/server_raw.stdout.log`
(`61abf3c49d34707309b098a315d62d7117679cc13074fb62ce6ecedc61047eb5`).

This is an ordinary import integration defect, not evidence against the
dual-cache hypothesis. No exactness, cache, timing, or endpoint result exists;
the component remains unconsumed and the endpoint was not run. The owner
released the bench to maintenance at 01:52:10Z. Conservative cumulative project
exposure is now `$1.76`, including `$0.15` for this 203-second H200 claim.
The narrowly scoped next repair is to bind the actual exported NGRAM worker
symbol, then re-run only the full-model component after director re-admission.
The local repair now imports `NGramWorker` from
`sglang.srt.speculative.eagle_worker`, matching the bound insertion-point
contract; its five behavioral tests pass (`6af827156d1526598c02828aa306b96f1e83c0a398c7b0e466f61080a08188fc`).

## 2026-07-26 — r5 repair expired pre-science

At 03:07:08Z the hash-bound r5 repair deadline (03:05Z) had elapsed. The
sole permitted previous cached server owner (PID 1486385) was absent; its
retained raw server artifact records the ordinary `NgramVerifyInput.verify`
integration failure and shutdown, with no component terminal, candidate CUDA
sample, or exact-c32 pair. A fresh replacement would not complete the pinned
full-model comparator within the expired bound and is prohibited by the r5
request. The claim is therefore released to maintenance; conservative
cumulative provider exposure is recorded as `$4.35`. Terminal:
`artifacts/ngram-readmission-20260726t0218z-r4-cached-restart/R5_REPAIR_DEADLINE_TERMINAL_20260726T0307Z.json`.

## 2026-07-26 — seq_lens_cpu repair launch invalid before request entry

Claimed the director-named H200 at 03:31:41Z, froze the project-local source
manifest, and installed the narrow `seq_lens_cpu` materialization in
`NGRAMWorker.forward_batch_generation`. The only permitted cached server
launched and was still in CUDA-graph capture when the controller submitted its
component requests. All 32 connections were refused before a request reached
the NGRAM worker; the `science_started` marker in the client is therefore not
sample evidence. The owner retrieved raw logs and released the bench ready at
03:34:17Z. No component or exact-c32 sample was consumed.

The causal amendment is that adapter attachment/container liveness is not
request readiness for this image; wait for the server's own post-graph-ready
signal before an admitted request. The one-server readmission allowance is
exhausted, so this is recorded as an infrastructure terminal rather than
replayed. Conservative cumulative provider exposure is `$4.67`.
## 2026-07-26 — readiness-gated cached replacement: request-manager timeout

Question: does the installed `seq_lens_cpu` repair permit the still-unconsumed
NGRAM component once the server has completed graph capture and is accepting
TCP connections?

Measured infrastructure: the retained H200 was claimed at 03:44:32Z.  The
single cached server recorded `Capture cuda graph end` at 03:46:07Z and `The
server is fired up and ready to roll!` at 03:46:15Z; its container remained
live and localhost:30000 accepted TCP.  The sole component invocation then
recorded `seq_lens_cpu_materialized=true` for nine rows, but all 32 requests
timed out in the tokenizer/request manager and returned HTTP 500.  No response
or comparator result persisted, and the server killed its process tree.

Decision: this is an invalid infrastructure/consumer attempt, not a component
sample.  Exact-c32 did not start.  Raw server output, component terminal, and
the four readiness witnesses are preserved in
`artifacts/ngram-readiness-gated-20260726t0343z/`; the H200 was released ready
at 03:48:36Z.  Conservative incremental exposure is $0.17 and cumulative
project exposure is $4.84.

## 2026-07-26 — CPU tensor correction reached a new pre-target allocator boundary

The admitted absent-only `seq_lens_cpu` correction now creates a CPU
`torch.int32` tensor.  The pinned-image contract artifact proves indexing,
`len()`, `.sum()`, dtype preservation, and stock-mirror preservation.  The
focused dual-cache tests also passed.  The named H200 was claimed at 04:00:53Z
and the sole corrected server passed CUDA-graph completion, server-ready,
container, and TCP gates.

The one component invocation failed before TARGET_VERIFY, candidate CUDA, or
a comparator result.  The actual new exception is `RuntimeError: proxy
allocator did not return a distinct logical slot vector` from
`ProductionDualCache.allocate`; all 32 client requests consequently returned
500.  This is a typed integration failure, not a scientific sample, and
exact-c32 remained closed.  Raw retrieval is preserved under
`artifacts/ngram-seqlens-cpu-tensor-20260726t0401z/`; terminal:
`SEQLENS_CPU_TENSOR_CORRECTED_COMPONENT_TERMINAL_20260726T0403Z.json`.
The bench released ready at 04:03:28Z.  Conservative incremental exposure is
$0.13 and cumulative project exposure is $4.97.

## 2026-07-26 — offline proxy allocator distinctness localization complete

Under `DIRECTOR_PROXY_ALLOCATOR_OFFLINE_LOCALIZATION_20260726T0411Z.json`,
the failure was reproduced without a GPU: a separately held backend allocator
starts at the same raw slot values as the scheduler-owned `batch.tree_cache`
allocator, so raw integer overlap is not a valid cross-owner distinctness
test. The repair selects the batch-tree allocator and its KV pool, and retains
native slot vectors instead of converting them to Python lists before the
attention, reuse, and free consumers.

`PROXY_ALLOCATOR_DISTINCTNESS_OFFLINE_TERMINAL.json` records passing
deterministic contracts for the bound 8,192-row EXTEND, 384-logical/512-captured
TARGET_VERIFY, accepted-slot reuse, rejected-slot free, and DECODE paths. The
old fixed-backend collision is explicitly falsified; no GPU was claimed, no
request was submitted, and cumulative provider exposure remains `$4.97`.

## 2026-07-26 — corrected allocator H200 component: pre-target exhaustion

Claimed the named warm H200 at 06:14:42Z under the corrected-allocator binding,
with a durable owner and project-local source manifest carrying the bound
`forward_batch_dual_cache_driver.py` hash `d0c33e76…`. The pinned one-model
server completed its ready signal and attached the driver. The single c32
submission then reached the stock EXTEND forward batch (`logical_rows=8192`)
but failed before TARGET_VERIFY or any candidate CUDA output: the new driver
attempted a full 8,192-slot proxy allocation and the tree allocator returned
no slots (`proxy allocator exhausted before logical-slot allocation`). All 32
requests returned HTTP 500, so no logits, accepted-prefix comparison, timing
comparison, or interpretable component result exists.

Raw consumer, retrieved server, readiness, and source-manifest artifacts are
under `artifacts/corrected-allocator-h200-component-20260726t0614z/` and the
typed terminal is `CORRECTED_ALLOCATOR_H200_COMPONENT_TERMINAL.json`. The
bench was released warm at 06:17:57Z with no server remaining. The two brief
claims consumed 237.998813 seconds at $2.45/hour, or `$0.1619714144`; the
project cumulative provider exposure is `$5.1319714144`. This is an ordinary
pre-target integration defect, not evidence against the proxy mechanism and
not a consumed scientific sample. A future readmission would need a fresh
binding for a target-only allocation/ordinary-stock-shadow repair; the
admitted claim window has closed.

## 2026-07-26 — target-only proxy allocator and owner-disposition repair passed

Under the amended target-only repair binding, proxy allocation is now a no-op
outside `TARGET_VERIFY`; the 8,192-row stock EXTEND fixture preserves all
allocator capacity. The 384-row target fixture receives a disjoint native
batch-tree vector, and accepted/rejected lifecycle finalization is exactly once
while post-accept decode stays stock. The prior eager 8,192-slot failure is
reproduced by the pre-repair branch and avoided by the repaired branch.

`target_only_proxy_allocator_component_owner.py` is hash-bound to the required
future command `python3 target_only_proxy_allocator_component_owner.py`. Its
four lifecycle fixtures prove that recoverable and unclassified pre-science
failures write repair-ready state without runtime removal or bench release,
whereas decision-bearing and absolute-deadline paths persist disposition before
cleanup/release. `TARGET_ONLY_PROXY_ALLOCATOR_REPAIR_TERMINAL.json` records all
eight passing fixtures. No GPU was claimed, provider contact occurred, or new
spend was incurred; cumulative actual spend remains `$5.1319714144`.

## 2026-07-26 — target-only component command lifecycle seam closed offline

Action: extracted the remote staging/start/readiness/TARGET_VERIFY/retrieval
path into `target_only_proxy_allocator_component_runner.py`, whose sole future
command is `python3 target_only_proxy_allocator_component_runner.py`. The
runner has no pool, runtime-cleanup, or repair authority. The outer owner now
requires a new binding to hash-verify its own bytes, runner bytes, allocator
bytes, absolute deadline, artifact root, and the current inventory connection
identity before it can attempt a claim.

Evidence: `TARGET_ONLY_COMPONENT_COMMAND_SEAM_TERMINAL.json` binds both future
commands and all three source identities. Twenty focused tests passed: fake
transport reached the typed pinned-consumer boundary without changing logits or
acceptance inputs; corrupt retrieval is typed non-decision-bearing; owner and
runner hash mismatches plus bench-identity mismatch stop before claim; and
recoverable/unclassified, decision-bearing, unsafe, and deadline branches take
only their declared lifecycle dispositions. No GPU was claimed, no SSH or
provider operation occurred, and no scientific component was started. Actual
project spend remains `$5.1319714144`.

Next: the director can issue the paid target-only readmission directly; this
offline seam action is complete.

## 2026-07-26 — retained-claim live join reached TARGET_VERIFY; request manager failed

The exact readmission owner claimed the warm H200 at 06:55:05Z, completed the
deliberate pre-science `server_launch_failed` bootstrap, and retained the claim.
The runner was repaired in place to stage a hash manifest, consume the actual
`forward_batch_dual_cache.json`, `adapter_attach.json`, and c32 invocation/
terminal records from the real `retrieved/artifact` layout, then atomically
submitted the fresh repair request to the same owner. The one resident target
server became ready at 06:59:20Z with its real ModelRunner forward hook
attached.

TARGET_VERIFY submitted the bound 32 requests, but each returned HTTP 500.
The durable live terminal records `complete: 0`, no accepted request, and no
candidate CUDA start. The preserved remote raw log shows SGLang request-manager
timeouts followed by its SIGQUIT handler terminating the process tree. This is
therefore a consumer/runtime integration failure with no interpretable target
logit or timing comparison—not scientific evidence and not a consumed sample.
The complete remote artifact was retrieved under
`artifacts/target-only-proxy-allocator-readmission-20260726t0648z/retrieved-failed-consumer-attempt/`.
The existing owner remains alive with its claim and retained-repair record;
because the named container exited and the already-running owner has no
repair-time replacement action, no replay was issued. Conservative cumulative
provider exposure through the observation is recorded as `$5.39` (below the
`$6.75` reservation); final exposure remains to be settled at owner cleanup.

## 2026-07-26 — retained owner reached deadline and released the H200

The detached owner is no longer live and its disposition is
`absolute_deadline_cleanup`. The lab pool records
`h200-dflash-adapter-e00vyqp7gxsr34wrtz` released at 07:24:02Z. Although the
expected `TARGET_ONLY_PROXY_ALLOCATOR_COMPONENT_TERMINAL.json` was not emitted,
the durable disposition, compact consumer terminal, raw server log, and the
retrieved remote artifact are sufficient to classify the event: all 32 target
requests returned HTTP 500, with zero completions, no accepted request, and no
candidate CUDA invocation. This is an infrastructure/consumer failure, not an
interpretable component result or a consumed scientific sample.

Spend settlement is derived from the owner interval 06:55:05.729209Z to
07:24:02.590657Z: 1,736.861448 seconds at $2.45/hour = `$1.1820307077`.
Added to the prior `$5.1319714144`, cumulative exposure is `$6.3140021221`,
leaving `$0.4359978779` of the `$6.75` ceiling. The project is blocked pending
a director-authorized replacement runtime and fresh lifecycle binding; the
failed consumer must not be replayed as another sample.

## 2026-07-27 — current-warm permanent 55L/5G endpoint controller implemented

Implemented `run_h200_55l5g_endpoint_pair.py` and
`run_h200_55l5g_endpoint_owner.py` under the 01:21Z offline readmission. The
pair binds the immutable 32-request, 4,214-prompt/358-output workload and
requires a runtime candidate-path proof for converted layers `[11,23,35,47,59]`
before sending the stock then candidate requests. It records per-request raw
text/token IDs, usage, finish reason, hashes, TTFT/decode fields, and timing
summaries. The owner binds the positive component source digest, exact $8.50
reservation, current bench identity, later lifecycle deadline, durable owner
bytes, and later stock/candidate activation commands; without that later
binding it exits before pool or SSH access.

`py_compile`, the current-readmission preflight, and the no-binding fail-closed
path pass. No GPU, SSH, container, request, or component invocation occurred.
The listed H200 is draining and its lifecycle expired at 01:32Z, so the next
move is a later director claim binding and lifecycle extension, not a claim or
endpoint replay.

## 2026-07-27 — retired H200 rebind repaired offline

The expired causal-head H200 is now rejected as an authority. The owner reads
the bench ID, accelerator/provider, complete SSH resource identity, checkpoint
path and manifest digest, image, claim generation, and release lifecycle from
a later director binding, then requires an exact match against a live,
available, unclaimed, non-retired H200 inventory row before it can reach the
atomic claim boundary. It records the pool-returned `claimed_at` as the
expected release guard and keeps the existing pair/repair contract unchanged.

The direct source hashes and focused checks are recorded in
`HYBRID_55L5G_RETIRED_BENCH_REBIND_TERMINAL.json`: compilation passed,
no-binding fails before provider access, the retired binding is rejected, and
a synthetic matching live row passes only the offline pre-claim boundary. No
GPU, SSH, endpoint, component, or provider action occurred. The project awaits
a later bounded lifecycle plus claim binding.

## 2026-07-27 — lifecycle extension request is not claim authority

The $10.00 cumulative reservation is present, but the 02:08Z request records
that the replacement watchdog and exact claim binding are still absent; the
live H200 inventory remains on its 02:39:55Z lifecycle. The owner now requires
a later binding with the $10.00 reservation, a verified watchdog identity that
matches the inventory, and the requested 03:10Z watchdog deadline before its
pre-claim boundary can pass. A synthetic matching extended lifecycle passes;
an otherwise matching binding without `watchdog_verified` is rejected.

`HYBRID_55L5G_LIFECYCLE_EXTENSION_REQUEST_TERMINAL.json` preserves the hashes
and the typed external boundary. No GPU, SSH, provider, component, or endpoint
work occurred. Once the director atomically updates the lifecycle and binds
the live bench, the owner must stage the cold immutable inputs inside the
retained claim and immediately continue to the single unconsumed endpoint pair.

## 2026-07-27 — bound extended-claim launcher failed before claim

Implemented the only authorized new source file,
`run_h200_55l5g_endpoint_runtime.py` (`e816f286…619e2a3`), and invoked the
exact detached-owner command from the 02:18Z binding at 02:22:30Z. The
detached-owner state was created as required, but its parent is also the
hash-bound owner's `artifact_root`; the owner calls `mkdir(exist_ok=False)` on
that root and exited with `FileExistsError` before it could access the pool.
The owner log is preserved at
`artifacts/h200-55l5g-extended-20260727t0218z/OWNER.log`
(`137f6c49…32de6188`). No claim, SSH, image pull, checkpoint transfer, GPU
work, request, or scientific sample occurred. This is a launcher-layout
contract defect, not evidence about the endpoint; do not replay the bound
command. A director must bind an owner/layout compatible with the mandated
detached state path before the still-unconsumed one-pair endpoint can run.

## 2026-07-27 — retained layout-repair owner reached a pre-science runtime boundary

The corrected owner claimed the H200 at `02:27:43Z` and its heartbeat remained
valid through `02:49:45Z`. It completed the hash-verified two-shard checkpoint
stage and pinned image pull; those producer facts are preserved at
`artifacts/h200-55l5g-extended-20260727t0218z/STAGING.json`
(`b73a2530…3df83e0a`) and `CANDIDATE_INSTALL.json`
(`9f9b767e…ffbf84fc`). The pair phase then raised the local
`runtime_pair_program_not_yet_retrieved` guard before SSH, server launch,
CUDA, or a request. The owner subsequently failed reading the absent old-root
terminal (`OWNER.log`, `4958afb3…e1862d7`). Therefore no endpoint arm was
consumed; the original 02:27:43Z claim is the only one and the warm staged
checkpoint/image must be retained. A replacement controller needs director
authority to adopt that claim and execute only the repaired runtime pair.

## 2026-07-27 — retained-claim adoption failed closed on binding metadata

The 02:55Z adoption controller verified the original claim and hash-bound the
runtime, pair, candidate source, workload, and resident markers. Before SSH
or any endpoint action, the corrected runtime rejected the authority because
the declared staging-marker digest (`…fa62806bbfa`) differs from the actual
named `STAGING.json` digest (`…8fa88fb23df83e0a`). This is repairable binding
metadata, not a model or endpoint result. The controller and runtime logs are
preserved under `artifacts/h200-55l5g-adopt{,-owner}-20260727t0255z/`; no CUDA
or requests were submitted and no staging was replayed.
