# Research log

## 2026-07-25 — H100 fit/economic packet

**Question.** Can the exact official v0.5.15 dynamic-FP8, E5M2 page-1 KV,
native depth-12 NGRAM stack plausibly fit and cross `$0.14/M` on one H100 SXM?

**Action.** Mechanically verified all seven `DIRECTOR_BINDING.json` identities,
the candidate's internal file manifest, the checkpoint geometry, the shared
H100 capability/price rows, and official v0.5.15 SM90/FP8/E5M2/NGRAM/fused-QK
source paths. Materialized the complete non-weight candidate under `packet/`
and added an H100-aware runner that evaluates startup fit, the 171-request
activation/semantic discriminator, and the conditional fresh-container
791-request endpoint.

**Evidence.** Measured, scope-matched H200 SM90 startup evidence records
`33.26 GiB` runtime weights, `0.05 GiB` pre-pool non-weight state, and
`1.43 GiB` CUDA graphs. Analytical Gemma geometry gives `40,960 B` per
full-attention token and `409,600 B` per sliding-window token. Treating the
inventory's 80 GB H100 capacity conservatively as decimal bytes leaves
`30.019935 GiB` for the default 0.8-ratio pools, an `87,439` full-token /
`69,951` sliding-token lower bound, 19 complete 4,572-token requests plus
depth-12 drafts, and `9.745871 GiB` post-graph headroom. This is an analytical
fit bound; H100 allocation and throughput remain unmeasured.

The exact denominators are 3,470,148 tokens for requests 32–790 and 3,616,452
tokens for requests 0–790. At `$2.80/GPU-hour`, `$0.14/M` permits respectively
`624.62664 s` and `650.96136 s`, both `0.82296 s/request`. At a sustainable
90% productive-utilization assumption, the ceilings are `562.163976 s`,
`585.865224 s`, and `0.740664 s/request`.

**Interpretation.** `nominate_one`. Capacity and official feature support clear
the offline gate with conservative headroom. No H100 performance is inferred
from H200; the packet requires direct H100 startup, activation, exactness,
queue, and endpoint-cost evidence.

**Next.** A director may reopen this project only with a positive spend
reservation, a registered 80 GB H100 SXM bench, and authority to materialize
the 62,578,655,208-byte manifest-bound checkpoint under this project before
the claim. Run the 171-request arm once; run the fresh-container 791-request
arm once only if every first-arm gate passes.

## 2026-07-25 — pre-create materialization terminal

**Question.** Can the director provisioning gate be opened without provider
mutation after the durable `$5` reservation and immutable checkpoint copy?

**Action.** Rechecked `DIRECTOR_EXECUTION_BINDING.json` and all 20 entries of
`PACKET_MANIFEST.json`. Copied the eight manifest-bound checkpoint files into
`inputs/checkpoint`, independently verified every declared byte count and
SHA-256, and removed write permission from the destination files. No H100
resource was created or claimed.

**Evidence.** The verified checkpoint is 62,578,655,208 bytes across eight
files; the packet manifest has 20/20 exact matches. The durable reservation is
the director-provided `$5.00` reservation at `2026-07-25T06:05:30.367822Z`;
project actual spend remains `$0.00`. Exact future image, runtime commit,
launcher, 171-request discriminator, and strictly conditional 791-request
endpoint are recorded in `PRECREATE_TERMINAL.json`.

**Interpretation.** The pre-create gate passes. This is preparation evidence,
not H100 performance evidence. Provider provisioning remains director-only.

**Next.** Director provisions/registers one H100 bench. The execution owner
then runs only the 171-request discriminator and runs the 791-request endpoint
once only if every discriminator gate passes.

## 2026-07-25 — staging complete; repair-1 owner active

**Question.** Can the bound H100 discriminator proceed after correcting the
owner's ordinary lifecycle and guest Docker invocation defects?

**Action.** The first owner completed local and remote checkpoint audits and
finalized the matched staging, but failed before server startup because its
heartbeat used an unsupported `--bench` option and the guest user lacked
direct Docker-socket permission. Preserved its typed terminal and diagnostics;
the 171-request invocation did not begin. Opened `repair-1`, patched heartbeat
syntax and used `sudo -n docker`, then requested one in-place retry with
`--reuse-staged`.

**Evidence.** Remote H100 identity was measured as `NVIDIA H100 80GB HBM3,
81559 MiB`; all eight remote checkpoint hashes passed. `sudo -n docker`
responds successfully. Repair-1 owner PID `459828`, start ticks `107842968`,
is live under `detached-owner --unit-manager pid`; the claim heartbeat was
renewed through `2026-07-25T07:45:00Z`.

**Interpretation.** The first attempt is an invalid harness attempt, not a
scientific sample. Repair-1 preserves the immutable remote staging and retries
only server startup plus the unstarted discriminator; the endpoint remains
strictly conditional.

**Next.** Reconcile repair-1 `TERMINAL.json` when the durable owner reaches a
scientific or typed terminal, then release the claimed bench.

## 2026-07-25 — repair-2 owner dispatched

**Question.** Can the unconsumed H100 171-request discriminator execute after
staging the missing immutable packet tree while reusing the healthy resident
server?

**Action.** Verified `DIRECTOR_REPAIR2_BINDING.json`, the execution/pre-create
bindings, and all 20 packet-manifest hashes. Atomically claimed the returned
H100 and confirmed one H100, the exact container digest/argv, and a healthy
`/v1/models` response. Started one durable repair-2 owner with packet staging,
resident-server reuse, explicit `UPSTREAM_REBASE_CONTAINER=gemma4-h100-v0515`,
and the 171-request scope.

**Evidence.** Owner PID `473021`, start ticks `107941285`, and owner state
`artifacts/h100-repair2-20260725t0709z/OWNER_STATE.json` are recorded in
`STATUS.json.active_session`. No candidate sample has been consumed; the
conditional endpoint remains disabled until all discriminator gates pass.

**Next.** Reconcile the repair-2 terminal and release the H100 by `07:35Z`.

## 2026-07-25 — repair-2 consumer retry active

**Question.** Can the staged packet consume the healthy resident server once
the runner environment survives `sudo`?

**Action.** Repair-2 staged and listed the complete packet tree and verified
the resident server, but its first consumer attempt failed before entering the
runner because `sudo` stripped `UPSTREAM_REBASE_ROOT`; no sample was consumed.
Preserved the terminal and stderr, opened the consumer repair handshake, and
patched only `sudo -n env` propagation plus the unsupported release argument.

**Evidence.** The H100 claim heartbeat is renewed through `07:45Z`. A single
durable consumer-repair owner is live as PID `477330`, start ticks `107965856`,
with matched packet/checkpoint staging reused and `candidate_sample_consumed`
still false.

**Next.** Reconcile the retry terminal, then release the H100 after the
scientific result or typed boundary.

## 2026-07-25 — H100 execution owner dispatched

**Question.** Does the exact official v0.5.15 native-depth-12 NGRAM stack fit
and execute on the registered H100 SXM under the bound 171-request contract?

**Action.** Verified `H100_BENCH_SPEC.json`, the execution binding and
pre-create terminal, all 20 packet entries, and all eight checkpoint sizes and
hashes. Atomically claimed bench `h100-v0515-ngram-e00mfea030cdngg54z` and
started one durable local owner under `detached-owner --unit-manager pid`.

**Evidence.** The provider instance is running as one `gpu-h100-sxm` with
public IP `195.242.29.133`; the owner PID is `440810` with start ticks
`107692392`, and its claim heartbeat is active. The owner artifact root is
`artifacts/h100-discriminator-20260725t0625z`.

**Interpretation.** No scientific sample is consumed yet. The owner is
performing the immutable staging and bound server startup; the 791-request
endpoint remains forbidden unless every 171-request gate passes.

**Next.** Let the same owner complete staging, H100/image verification, and
the 171-request discriminator, then retrieve its terminal and release the
bench by the bound deadline.

## 2026-07-25 — offline H100 observer repair ready

**Question.** Does the fail-closed H100 fit observer accept the official
v0.5.15 target-verification CUDA-graph log wording while still rejecting the
legacy/malformed wording that caused the pre-sample boundary?

**Action.** Patched `packet/h100_matched_runner.py` to centralize fit-log
parsing and accept `Capture target verify CUDA graph end`, retaining strict
field presence and fit gates. Replayed the parser against the persisted
repair-2 `SERVER.log` and a negative fixture containing only the old
`Capture cuda graph end` form. Regenerated all 20 entries of
`PACKET_MANIFEST.json` and emitted one repair-handshake `REPAIR_READY.json`.
No GPU was claimed or touched.

**Evidence.** The positive persisted log parses as `full_layer_tokens=97361`,
`swa_layer_tokens=77888`, graph use `1.06 GiB`, and post-graph available
memory `10.63 GiB`; all fit gates pass. The negative fixture is rejected
fail-closed with `fit_log_field_missing:post_graph_available_gib`. The ready
artifact hash is
`0e952c5f80754a0858f4f467097d2799088c57022895872c719b7a9e2b0aeb59` and its
diagnostic binds the patched runner, regenerated manifest, positive log, test,
and negative fixture hashes.

**Interpretation.** The prior H100 attempt was an ordinary observer
integration defect, not a scientific sample; the 171-request discriminator
remains unconsumed. The repair is ready for director review and a fresh bound
consumer retry; the endpoint remains conditional.

**Next.** Await a new director binding. Do not claim the maintenance H100 or
replay any request from this project.

## 2026-07-25 — repair-3 pre-sample staging boundary

**Question.** Can the observer-repaired packet be reconciled onto the returned
H100 and reach the unconsumed 171-request discriminator while reusing the
healthy official server?

**Action.** Verified `DIRECTOR_REPAIR3_BINDING.json`, all six bound repair
files, all 20 local packet entries, and all eight checkpoint hashes. Claimed
the registered H100 and launched durable controller PID `492055` with the
observer-repaired packet, `--reuse-staged`, `--stage-packet`,
`--reuse-server`, and explicit container identity.

**Evidence.** Local audit passed; remote preflight measured `NVIDIA H100 80GB
HBM3, 81559 MiB`; remote checkpoint and packet staging hashes passed. The
attempt stopped before server reuse and before candidate CUDA because the
owner's remote packet-reconcile wrapper appended shell commands after a
here-document terminator, producing a Python syntax error. Preserved terminal
`artifacts/h100-repair3-20260725t0730z/TERMINAL.json` (SHA-256
`28baf074e76cf04944dd564234ba5a39bfe0a265fb428c231dd731197f8612a9`). The
H100 claim was released to maintenance. Conservative cumulative provider
exposure is recorded as `$3.60`, including the project's prior H100 allocation
window and failed attempts; no sample or endpoint was consumed.

**Interpretation.** This is an ordinary owner-wrapper integration defect, not
placement or scientific evidence. The repaired observer remains valid, but
the 171-request discriminator must not be replayed until a director binds a
corrected reconciliation owner.

**Next.** Preserve the warm official server and diagnostics; await a deliberate
owner-wrapper repair binding. Do not claim or replay this project in the
current turn.

## 2026-07-25 — endpoint-only replacement-H100 handoff

**Question.** Can the one unconsumed 791-request endpoint be run after the
valid 171-request discriminator without replaying that consumed discriminator?

**Action.** Reconciled the updated director state. The cumulative project
reservation is durable at `$9.00`; current conservative project exposure is
`$4.94674`. Checked the shared inventory for the named H100 once.

**Evidence.** The prior repair-5 discriminator is valid and consumed:
171/171 exact, zero failures, native depth-12 activation, queue peak 14,
final queue 0, `0.7073339939 s/request`, and approximately `$0.133700/M`.
The 791-request endpoint remains explicitly unconsumed, but the prior H100
instance and disk are absent and its inventory record is retired. No compatible
replacement H100 is registered; the live H200 is unrelated and cannot satisfy
this endpoint contract.

**Interpretation.** This is a director-owned resource boundary, not endpoint
evidence. No provider creation or claim is authorized for this researcher
turn, and the consumed 171-request arm must not be replayed.

**Next.** Director must create/register one replacement 80-GiB H100 protected
through `09:15Z`; then a bounded owner may stage the exact packet and run only
the 791-request endpoint once, releasing by `09:10Z`.

## 2026-07-25 — endpoint recovery stopped at external SSH preflight

**Question.** Can the registered replacement H100 stage the exact bound
checkpoint/image/packet and run the one remaining 791-request endpoint?

**Action.** Verified the endpoint-only owner contract, atomically claimed the
replacement H100, and launched durable owner PID `533826` with the exact
endpoint-only packet. Reconciled its terminal after the owner stopped.

**Evidence.** Local immutable audit passed (`8` checkpoint files and `20`
packet entries). Remote preflight failed before any staging, container start,
CUDA, or endpoint request: `ssh: connect to host 195.242.29.133 port 22:
Connection timed out`. Preserved terminal
`artifacts/h100-endpoint-20260725t0816z/TERMINAL.json` with SHA-256
`1f9d9862bdc505910902e1c9ea41859493c85b6632ad216762d05b8c2a238ddc`.
The owner released the H100; inventory reconciliation now shows it available.
Conservative added provider
exposure was `$0.2611202563`, from registration through the typed preflight
boundary; cumulative project exposure is `$5.2078602563`.

**Interpretation.** This is an external/recoverable reachability boundary,
not endpoint evidence. The 791-request endpoint remains unconsumed, and the
valid 171-request discriminator remains consumed; no replay is permitted.

**Next.** Director inspection/recovery of the replacement H100 is required
before another endpoint-only owner is authorized.

## 2026-07-25 — endpoint disk-repair owner stopped before image validation

**Question.** Can the retained H100 recover only expendable failed-pull state,
prove space for the exact pinned image, and run the sole unconsumed 791-request
endpoint without replaying the consumed 171-request discriminator?

**Action.** Verified the disk-repair binding hashes, claimed the registered
H100 once, and ran the bounded PID-managed owner against the registered
`glmrunner@89.169.112.211` identity. The owner reclaimed only the authorized
Docker/cache classes and preserved the immutable checkpoint.

**Evidence.** Cleanup reclaimed `0B`; Docker reported no images, containers,
volumes, or build cache. The guest had `22,307,127,296` free bytes. The owner
then stopped before the pinned image pull because its manifest-size inspection
returned `image_manifest_size_unavailable`. Terminal:
`artifacts/h100-endpoint-diskrepair-20260725t0955z/TERMINAL.json` (SHA-256
`11ee200be8a1b455b4e4d6e8a3a55a2b2b2f2fc4aab527cc1f10406552fe9a95`); stderr
SHA-256 `a1ad236c474e09e0a22a69b4290fa52690f58c0f38c2ae58f4fdaea92984fb92`.
No server, CUDA invocation, or endpoint request began; the 791-request arm is
unconsumed and the 171-request arm remains forbidden to replay.

**Interpretation.** This is an ordinary harness/parser defect, not scientific
evidence and not proof of insufficient disk capacity. The owner released the
bench to maintenance after the typed pre-science terminal.

**Next.** Preserve the checkpoint and diagnostics. Director must bind a
corrected manifest-size repair before another owner launch; do not chain a
replacement owner in this turn.

## 2026-07-25 — exact-digest manifest-size parser repair ready

**Question.** Can the invalid `image_manifest_size_unavailable` observation be
repaired offline without treating it as a disk-capacity result or touching a
provider resource?

**Action.** Mechanically verified `DIRECTOR_PARSER_BOUNDARY_CORRECTION.json`
(SHA-256 `0994817aac66ac83f8f8baafd767eb57147d5bb87b0b9b4a0ce7d679d54cb325`)
and `DIRECTOR_MANIFEST_SIZE_REPAIR_BINDING.json` (SHA-256
`05fce9781a277534370994b0e091abfc14b66a5a4a8fc65aec72700479876516`). Added
the exact-ref, schema-aware, fail-closed parser in `manifest_size.py` and
bound the same checks into the future owner path. No GPU claim, provider
mutation, or workload launch occurred.

**Evidence.** The content-bound positive fixture produced compressed-byte total
`600` twice, with deterministic equality and a sufficient-space fixture
decision. Missing size, malformed numeric size, duplicate descriptor digest,
digest-mismatched ref, and missing schema all failed closed. Results are in
`artifacts/manifest-size-repair-20260725t1005z/FIXTURE_RESULTS.json` (SHA-256
`ebfe5c4104b2f5ccdafec9098350139e86fc413adc4d6120669058d4fde17638`). The
repair source hash is
`e8b3db6aee01466d8d66180cf101df10616d85b8d8cb4adbe5c933c7fcfdf083`.

**Interpretation.** The prior attempt remains an invalid pre-sample parser
observer failure; physical 100-GiB fit is unknown. The 791-request endpoint
is unconsumed and the 171-request discriminator remains forbidden.

**Next.** `REPAIR_READY.json` is persisted at the project root (SHA-256
`458dbc61a9b0fe8721f3dd93d39f6c491cf2ae90b73748f0eafb53b178871a70`). A
director-owned future H100 allocation may be considered only after this
offline gate; this turn created no resource and launched no workload.

## 2026-07-25 — 200-GiB H100 claim blocked by draining pool state

**Question.** Can the repaired exact-digest path proceed on the registered
200-GiB H100?

**Action.** Verified `REPAIR_READY.json` and
`DIRECTOR_200GIB_ENDPOINT_BINDING.json`, then attempted the required atomic
claim for `h100-v0515-endpoint-200g-e00wthpm1fp735xd44`.

**Evidence.** The pool reported `no available GPU bench matches this project`
because the registered bench status is `draining`. The claim did not succeed;
no SSH connection, checkpoint staging, image inspection, server start, CUDA
invocation, or endpoint request occurred. Diagnostic:
`artifacts/endpoint-200g-claim-20260725t1023z/CLAIM_ATTEMPT.json`.

**Interpretation.** This is a typed external pool boundary, not scientific
evidence. New provider exposure is `$0`; the 791-request endpoint remains
unconsumed and the 171-request discriminator remains forbidden.

**Next.** Director must make the registered bench claimable or issue a typed
terminal. The researcher will not bypass `draining` state or mutate the
provider.

## 2026-07-25 — SSH identity correction completed the sole endpoint

**Question.** Does the exact official SGLang endpoint complete on the retained
H100 when launched with the registered Nebius SSH identity?

**Action.** Verified `DIRECTOR_R2_SSH_IDENTITY_CORRECTION_BINDING.json`,
claimed the retained bench once, and launched the unchanged durable owner with
`/root/.config/nebius/glm-campaign/ssh_ed25519`, `--reuse-staged`, and no packet
restage. The prior missing-key failure was preserved as a controller defect.

**Measured evidence.** The sole 791-request endpoint completed with zero
request failures, 3,616,452 total tokens, 617.580 seconds elapsed, 0.780758
seconds/request, queue peak 22 and final 0. The exact pinned image measured
18,969,730,141 compressed bytes with 126,320,873,472 free bytes and a passing
space gate. Planning cost was `$0.132821/M` total tokens; sustainable cost was
`$0.147579/M` against the `$0.14/M` target. Native NGRAM activation was
observed, but normalized semantics were not exact: first divergence was
request 277, output token 19; placement also failed. Terminal:
`artifacts/h100-endpoint-200g-r2-ssh-identity-correction-20260725t1140z/TERMINAL.json`
(SHA-256 `31b093640b65eb4f45a65462cfc34ef833f239c1da73bc68d73eba0fd5c68927`).

**Interpretation.** This is a valid scientific endpoint terminal and consumes
the sole 791-request arm exactly once. The quality/placement and sustainable-
cost gates fail; the 171-request discriminator remains consumed and forbidden
to replay. The H100 bench was released available and cumulative conservative
provider exposure is `$10.86`.
