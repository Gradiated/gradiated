# Research log

## 2026-07-24 — measured-v1 exposed the unpatched production consumer

**Question.** Can a 12x12 QLEN-only target-verification mask preserve the pinned
Triton endpoint and reduce c32 service time?

**Action.** Hash-checked every `DIRECTOR_BINDING.json` dependency, froze one
QLEN intervention, claimed only
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`, and ran the sliding/full component
before the one conditional profiler-off c32 pair. The PID-managed outer owner
retrieved the complete terminal before releasing the bench.

**Measured evidence.** The staged component reported bit-identical BF16 outputs
for its non-unified sliding/full calls. Mask booleans fell from `1,622,784` to
`4,608`; median mask preparation fell from `0.518496 ms` to `0.022464 ms`;
sliding attention fell from `1.386240 ms` to `1.326144 ms`; full attention fell
from `4.139296 ms` to `4.099712 ms`; its derived positive bound was `2.4609%`.
That admitted the pair. Both endpoint arms completed 32/32 with stable servers
and identical request, finish, usage, and token-count accounting, but only one
of 32 normalized texts matched. Candidate service time was `0.800498049 s/req`
versus `0.604980623 s/req` control (`+32.3179%`); p95 was `25.039781 s` versus
`19.257202 s` (`+30.0281%`). Provider exposure was conservatively
`$0.199526`.

**Causal amendment.** This is an ordinary integration defect, not evidence
against the intended QLEN contract. Source tracing after retrieval showed that
the endpoint calls `extend_attention_fwd_unified`, while measured-v1 patched
and benchmarked `extend_attention_fwd`. The actual unified kernel still loaded
the compact mask with `row * cur_seq_kv_len + column`, reading beyond the
4,608-byte candidate buffer. The zero candidate-path audit rows agree with the
missing production-consumer proof. The complete malformed pair is preserved in
`FROZEN_PACKET.measured-v1.tar` and is not eligible for unchanged replay.

**Repair and blocker.** Repair-v2 applies the QLEN mask only to unified extend
positions, leaves prefix positions implicitly allowed, and changes the
component to call the actual unified consumer. It is frozen as
`FROZEN_PACKET.repair-v2.tar` with SHA-256
`977d5b5cf7b7d8bdb317beaa2ab67d0b69bcb1e61b499545e8d5a5d0db3a57be`.
The first pool release path faulted after terminal retrieval; the fallback
maintenance release succeeded. The bench is unclaimed in `maintenance`, so
target-GPU repair validation now requires director inspection and an explicit
return to `available`.

## 2026-07-24 — repair-v2 reached the actual unified consumer and failed sliding exactness

**Question.** Does the frozen unified suffix-mask repair preserve both exact
component consumers, permitting the one invalidated candidate-only endpoint?

**Action.** Materialized the persisted measured-v1 control as an immutable
project-local snapshot, then used one detached PID-managed owner to claim the
retained H200 and run the hash-bound repair-v2
`extend_attention_fwd_unified` sliding/full component. A narrow adapter
prevented the packet's obsolete fresh-control endpoint runner from replaying
the settled control. The remote compact terminal, stdout/stderr, invocation
marker, and final archive (SHA-256
`f5ff8f0039aab00f09d16f34f4b63bbe3cef2bced499cfec166ba6a66de01141`) were
retrieved after the owner encountered a duplicate-release/retrieval-path
defect.

**Measured evidence.** The actual component executed and persisted its
scientific marker. Mask preparation again fell from `0.496000 ms` to
`0.022400 ms`, and its derived whole-request bound was positive at `6.61895%`.
Full attention was bit exact. The 1024-token sliding consumer was not exact:
`max_abs_error=0.139404296875`, `mean_abs_error=0.00358017`, and
`relative_l2=0.10284337`, failing the frozen allclose oracle. It therefore
reported `component_pass=false`; no endpoint was invoked and the persisted
`0.6049806232813353 s/request` control was not replayed.

**Interpretation and next move.** This is a scientific terminal for the
QLEN-only unified realization: the repair is insufficient for local/sliding
suffix addressing, even though full attention and the representation-cost
bound are positive. Preserve the exact artifacts at
`artifacts/qlen-mask-20260724t163813z/retrieved-final/artifacts/`; any further
repair needs a new director disposition. Cumulative conservative provider
exposure is `$0.2206263662` (`$0.1995261184` measured-v1 plus
`$0.0211002477` repair-v2).

## 2026-07-24 — observer-v3 fixed sliding comparison; endpoint candidate path remains unproven

**Action.** The first V3 staging attempt consumed no scientific invocation:
root-owned files from an earlier container prevented cleanup of the old remote
artifact directory. Its `$0.0083731935` exposure is included below. The repair
used a new project-specific remote root, preserved the hash-bound repair-v2
candidate (`68149643…ec6e7`), and ran only the director-specified window-sliced
sliding component. It reused the already-consumed exact full row and mask
preparation evidence, then ran the one conditionally admitted candidate-only
endpoint against the persisted control (no fresh control replay).

**Measured evidence.** The corrected unified sliding control had the required
`1036` row stride and `12432` mask-indptr stride. It was exact (`max_abs=0`,
relative L2 `0`) and 5.8127% faster for sliding; with the persisted exact full
row and preparation timing, the bound was positive at 6.55934%. The endpoint
completed its 32 candidate requests but reported zero candidate-path audit
rows, `semantics_match=false`, `0.808822531 s/request` versus persisted
`0.604980623 s/request` (+33.69396%), and p95 +33.4647%. Its raw terminal and
compact retrieval archive (SHA-256
`4fe3a5797dacfcd478d37d905da4e014b695c716267ec83dabc30cebedfb02a9`) are
at `artifacts/qlen-mask-20260724t165142z/retrieved/`.

**Interpretation.** The component result establishes that the unchanged
repair-v2 QLEN representation is exact for the corrected unified sliding and
persisted full consumers. The endpoint does not establish a candidate result:
its zero candidate-path rows leave the mounted candidate consumer unproven,
and its semantic mismatch is therefore an integration observation rather than
a valid performance conclusion. Do not replay either endpoint arm unchanged;
the next repair requires a director disposition. Cumulative conservative
provider exposure is `$0.3501069216`, including `$0.0083731935` invalid
staging and `$0.1211073619` for V3.

## 2026-07-24 — director reactivation: bind the stock two-stage branch

The later ring-stack terminal exposed a decisive source fact that was missing
from observer-v3: the persisted candidate endpoint launch did not enable
deterministic inference. The endpoint therefore selected the normal two-stage
`extend_attention_fwd` branch, while observer-v3's exact component exercised
`_forward_extend_unified`. The endpoint's zero candidate-path rows and
semantic mismatch consequently cannot close the 6.55934% exact QLEN bound.

Priority 7520 reactivates this project under its cumulative `$6` authority.
`DIRECTOR_PRODUCTION_BRANCH_REPAIR.json` binds the launch, sources, observer
terminal, ring terminal, persisted control, and exact retry scope. Run one
real first-call production-branch discriminator; only an exact positive
result admits one candidate-only c32 endpoint. The control and every prior
component or endpoint remain consumed.

## 2026-07-24 — director redirect: implement the admitted runner

The first stable-packet continuation hash-checked every binding but returned
after observing that no production-branch runner had been supplied. That
31-second turn created no artifact, claim, invocation, or scientific row and
consumed no arm. `DIRECTOR_EXECUTION_CLARIFICATION.json` now makes explicit
that implementing the narrow captured-call adapter is the delegated work.
Reuse the existing component and candidate scripts, launch a controller-host
durable owner, and keep ordinary integration repairs inside its claim.

## 2026-07-24 — director routing: deep branch localization

The clarified execution continuation returned after 11.581 seconds with only
“unable to complete,” despite first committing to implement and launch the
runner. It inspected no source, wrote no project artifact, made no claim, and
produced no typed blocker. Across three consecutive continuations, no GPU arm
or scientific evidence was consumed.

The same production-branch question is now priority 7530 with profile `deep`.
This routing is justified by the required causal mapping across the bound
two-stage dispatch, actual c32/Q12 mask and KV geometry, and H200 consumer.
Scientific gates, cumulative `$6` authority, persisted control, warm bench,
20:00Z watchdog, and 19:50Z release remain unchanged.

## 2026-07-24 — two-stage runner implemented; lifecycle defect blocks the real sample

**Question and action.** Traced the normal dispatch through
`TritonAttnBackend.forward_extend` into the two-stage
`extend_attention_fwd`, implemented a live captured-call hook from the two
seed scripts, fixed the missing CUDA-graph QLEN `mask_indptr` stride in the
candidate backend, and added a nonzero normal-branch endpoint audit. Frozen
packet `FROZEN_PACKET.production-two-stage.tar` has SHA-256
`80a0a8b3878a10c600ba48678dd091f25758385389b148caf5c022bb1b5ae0ce`.
One controller-host PID owner claimed the retained H200, preserved and
stopped the named ring server after claim, staged the packet, and launched
the component.

**Invalid attempt and amendment.** The first hook fired during CUDA-graph
capture on setup buffers: its mask row stride was `13` and each request had
one KV index, rather than the admitted approximately 4214-token first real
c32/Q12 call. The resulting exact/positive row at
`artifacts/qlen-mask-20260724t185313z/retrieved/artifacts/component/COMPONENT_TERMINAL.json`
is preserved but is not a scientific sample. The amended hook rejects mask
strides below `4000`; the component trigger alone disables CUDA graph to
expose the unchanged normal two-stage kernel on the real request, while the
conditional endpoint retains the exact stock launch. Neither scientific
component nor endpoint was consumed.

**Typed blocker.** During the same-claim repair, the outer owner's second
retrieval attempted to create its already-existing local `retrieved/`
directory, raised `FileExistsError`, and incorrectly released the bench to
`maintenance`. Conservative cumulative project exposure is now
`$0.6107086696`. The post-release component never reached its invocation
marker; PID `115183` and its temporary container were stopped after
identity verification, leaving the accelerator unoccupied. Researcher
authority cannot move a maintenance bench back to available. The director
must inspect/ready this same bench; then the corrected component and only
its conditionally admitted candidate endpoint can run without replaying a
valid sample.

## 2026-07-24 — director clearance: run the corrected real-call packet

A one-time maintenance inspection confirmed the guest owner dead, no running
container, no GPU compute process, and an unoccupied accelerator. The H200 was
returned to available with its resident checkpoint, image, and caches intact.

The same project is active at priority 7540 with profile `execution`.
Source-level causal work is complete; the next action is the already-frozen
real-call component in packet
`80a0a8b3878a10c600ba48678dd091f25758385389b148caf5c022bb1b5ae0ce`,
followed only conditionally by the candidate endpoint. The dummy capture,
control, unified component, and all prior endpoint arms remain forbidden.

## 2026-07-24 — corrected real-call owner active

**Action.** Hash-verified the admitted production-two-stage packet, claimed
the returned H200, and launched the controller-host PID owner recorded in
`artifacts/qlen-mask-20260724t1911z-real-c32/controller-owner.json`. It uses
a fresh glmrunner-owned remote root and immutable content-addressed retrieval
snapshots.

**Repair.** The initial component setup reached a container-created,
non-writable artifact subdirectory before the trigger; its retrieved snapshot
records `scientific_invocation_started=false`. The claim stayed warm. The
directory ownership was repaired and the component-only retry was requested
through the shared repair handshake. No component or endpoint sample has been
consumed; the retry remains under the same durable owner.

## 2026-07-24 — real two-stage component passed; endpoint comparator repair active

**Measured component.** The repaired first real c32/Q12 call persisted both
normal two-stage rows with BF16 outputs, page-1 E5M2 KV, `4226` mask-row
strides, and bit-exact output/first-logit evidence. The QLEN mask is `4,608`
bytes versus `1,622,784` full-mask bytes. The measured weighted bound is
`+0.1426789712%`, admitting the candidate-only endpoint.

**Endpoint repair.** The first candidate-only 32-request execution persisted
the component and candidate request artifacts, but crashed after completion
while indexing absent stream `token_ids`. Its incomplete pair root is retained
as `pair-invalid-normalizer-20260724t1919z` with its candidate terminal hash.
The bounded retry changes only the endpoint normalizer to record unavailable
token IDs as an invalid comparator condition rather than raising; it resumes
from `COMPONENT_PERSISTED.json` under the existing owner and claim.

## 2026-07-24 — director close after the bounded endpoint

The real production two-stage component is valid and retained: both local and
global rows were bit-exact at the actual c32/Q12 geometry, and its weighted
whole-request bound was `+0.1426789712%`. The single admitted candidate
endpoint exercised one audited two-stage row and measured
`0.6049099965 s/request` against persisted `0.6049806233`, only
`0.0116742%` faster. Stream token IDs were unavailable, so exact endpoint
semantics could not be established; the bounded normalizer repair is consumed
and no endpoint replay is authorized.

Close this QLEN production realization as nonpositive/invalid. Preserve the
component as exact mechanism evidence, but do not stack it into the production
baseline. The next portfolio line is the materially different SWA/KV pressure
transition that controls sustainable NGRAM throughput.
