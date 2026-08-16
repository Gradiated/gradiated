# Research log

## 2026-07-25 — one upstream runtime nominated

**Question.** Does official upstream contain one newer unmodified runtime with
a causal NGRAM/tree-verification/cache-position change that retains the bound
Gemma 4 31B native FP8 depth-12 path?

**Action.** Mechanically verified all five `DIRECTOR_BINDING.json` inputs,
fetched official SGLang HEAD and stable releases v0.5.14–v0.5.16, traced the
bound Triton NGRAM proposal → tree reconstruction → target verify → accepted-KV
move/commit → request cleanup → Gemma local/global attention → CUDA-graph path,
and froze v0.5.15 plus a 171-request execution packet. No GPU was claimed and
no provider or paid resource was mutated.

**Evidence.**

- Measured/bound: all director input hashes match; the retained support-two
  endpoint is economically positive at `$0.1393159641142523/M` but semantically
  rejects at request 790.
- Source-derived: pinned v0.5.13 uses NGRAM spec-v1, where
  `NgramVerifyInput._free_cache` owns accepted-KV selection/move, request KV
  watermarks, and request-to-token mapping. Upstream commit
  `111009ea542e3430d8eed6e8e99dd8558982699f` replaces that state transition
  with NGRAM spec-v2. Commit
  `854c688121ed29f49bc862fe19357eecd6c72b30` makes the scheduler the single
  owner of full accepted-run KV settlement and adds an ownership guard motivated
  by premature SWA eviction.
- Content identity: selected release commit
  `f63458b5beaceabbd9d749b9fc956370e1b649e6`; official CUDA 12.9 amd64 image
  `docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd`.
  Registry labels bind that image to the selected commit.
- Source support: the frozen source retains native NGRAM with default draft
  depth 12, FP8 quantization, FP8 E5M2 KV, Gemma sliding/global attention,
  Triton target verification, and NGRAM CUDA-graph capture. The packet manifest
  verifies 27 files with zero failures.

**Interpretation.** Nominate exactly v0.5.15. It is the first stable release
with the complete causal state-transition replacement and single-owner
settlement. v0.5.14 is an intermediate bookkeeping state; v0.5.16 and current
HEAD retain the repair but add unrelated drift. This is source-backed
capability, not a claim that semantics or economics transfer across runtimes.

**Next move.** Await separate director spend/bench authorization after the
priority-8500 predecessor releases. Then stage the immutable packet, launch the
digest-pinned image with unchanged bound flags, and run only requests 0–170 at
bound arrivals. Require exact semantics, zero failures, bounded release drift,
and observed native NGRAM acceptance. Only a full pass admits one unmodified
791-request endpoint under the existing `$0.14/M` and queue gates.

## 2026-07-25 — pre-request consumer repair preserved; owner lifecycle boundary

**Action.** The retained H200 pulled and launched the official bound v0.5.15
image, then the discriminator failed before its request loop because its
host-side Docker inspection used an unprivileged client. The compact remote
terminal, guest log, pre-replacement container inspection, and invocation
state were retrieved. The repair patch runs only the discriminator under
`sudo` and detects/reuses the healthy named server so a later repair cannot
reload the image/model.

**Evidence.** `ATTEMPT_TERMINAL.json` records `candidate_sample_consumed:
false`; `INVOCATION_STATE.json` records `science_started:false`; the guest log
records the verified official image digest and the precise Docker-socket
permission failure. The first local owner had a pre-remote inventory-shape
defect; its single replacement then wrote `REPAIR_READY.json` but exited,
leaving no durable process to consume `REPAIR_REQUEST.json` or heartbeat the
claim.

**Interpretation.** No scientific sample is consumed. The Docker permission
error is an ordinary consumer defect, but the dead outer owner is a typed
lifecycle boundary: a repair request would be unserviceable and the same
turn may not launch a further replacement owner. The claim is returned to
maintenance with the v0.5.15 server resident for deliberate director recovery.

**Next move.** A new director-authorized owner may use `REPAIR_PATCH.json` to
run only requests 0–170 against the resident server, preserving the retrieved
failed attempt and applying the original conditional endpoint gate.

## 2026-07-25 — official v0.5.15 discriminator passes

**Action.** The director-authorized recovery owner applied the single bound
`sudo docker inspect` patch, removed only the audited port-30000 legacy
container and exited v0.5.15 container, launched the official digest-pinned
v0.5.15 image, and ran requests 0–170 once.

**Evidence (measured).** `FINAL_TERMINAL.json` records all 171 requests
complete with zero failures, exact normalized semantics, bounded release
drift, observed native NGRAM activation (`max_spec_accept_length: 12`), no
semantic divergence, and 119.896 seconds elapsed. It sets
`endpoint_admitted: true`.

**Interpretation.** The source-level v0.5.15 rebase clears the short semantic
discriminator. A stale attempt marker coexists with the complete final
terminal; the latter is decision-bearing and consumes this discriminator
sample. The recovery owner released before the conditional endpoint stage;
the binding forbids a chained replacement owner, so this is an orchestration
boundary, not authority to claim again.

**Next move.** Director authorization is required for a distinct endpoint
owner/session that reuses the resident v0.5.15 server and runs the one
admitted 791-request endpoint under the original queue, trunk, and `$0.14/M`
gates.

## 2026-07-25 — endpoint controller false-terminal boundary

**Action.** The bound endpoint packet verified and the H200 was claimed. The
endpoint-only guest began its single 791-request invocation without replaying
the discriminator or reloading the resident server.

**Evidence.** Remote `INVOCATION_STATE.json` records `science_started:true`
and `requests:791`; guest PID `74086` / start ticks `2174809` remains live.
The local controller matched the literal string `ENDPOINT` in its own
`ENDPOINT_OWNER` status output, falsely treated it as `ENDPOINT_TERMINAL`, and
released the bench before retrieval. The pool therefore rejects reacquisition
because the bench is now maintenance.

**Interpretation.** The endpoint may yet produce a complete consumable
sample, but no terminal was retrievable at the boundary. It must not be
replayed. This is a typed ownerless-live-guest lifecycle defect requiring the
director to restore a claim/controller solely for terminal retrieval.

## 2026-07-25 — official v0.5.15 endpoint retrieved: valid rejection

**Action.** The director-bound retrieval owner verified the recorded guest
identity (`PID 74086`, start ticks `2174809`), copied its already-persisted
terminal and request rows without launching a worker, sending a request, or
mutating the resident server, then released the H200 to maintenance.

**Evidence (measured).** The retrieved terminal is SHA-256
`7e6ba230931ccf0db83917ae0797e89c4fe983d6f53923fa1fcb84e744893367` and
records all 791 requests, zero failures, native NGRAM activation, queue peak
14, final queue 0, and planning cost $0.143754898/M. Its required gates fail
for normalized semantics, long unaffected trunks, and the $0.14/M cost cap.
The bound owner JSON hash matches the director binding:
`864b865c0c724388d047d71ba95195acf9c66ad394174ed1e3c1f0abefe0c833`.

**Interpretation.** This is the sole consumed endpoint sample and is a valid
runtime-trajectory rejection. The early retrieval controller's inventory
shape bug happened before it contacted the guest; its one repaired retrieval
owner collected the persisted result. No replay is authorized.

Artifacts:

- `DIRECTOR_BINDING_VERIFIED.json`
- `artifacts/candidate-v0.5.15/CANDIDATE_RUNTIME.json`
- `artifacts/candidate-v0.5.15/SOURCE_PATH_CAUSAL_MAP.json`
- `artifacts/candidate-v0.5.15/UPSTREAM_AUDIT.json`
- `artifacts/candidate-v0.5.15/SHA256SUMS.json`
- `remote_runtime_discriminator.py`
