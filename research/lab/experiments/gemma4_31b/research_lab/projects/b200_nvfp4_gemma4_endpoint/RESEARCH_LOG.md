# Research log

## 2026-07-28 — native endpoint packet

Question: can the exact Gemma 4 revision use the predecessor's native W4A4
NVFP4 path in a complete B200 c32 endpoint rather than only in isolated
linears?

Action: consumed predecessor terminal `0838a226…`, read the pinned
compressed-tensors dispatch contract, and implemented the immutable packet at
`artifacts/native-nvfp4-endpoint-packet-v1`. It binds the 62,578,655,208-byte
eight-file checkpoint, tokenizer/template hashes, pinned image/commit, c32
4214/358 workload, conservative 300-GiB disk / 90-minute owner request, and
same-session B200 BF16 control. The worker atomically copies verified bytes
under its project root before conversion, verifies the W4A4 symmetric-float4
group-16 contract, and launches the pinned runtime with compressed-tensors.

Evidence: `PACKET_MANIFEST.json` SHA-256
`707b20f442ade965a9970d3338d8b608946cf4e3168fa7257111963b38f0b116`;
Python compilation and shell syntax passed. The exact vLLM source semantics
require NVFP4 weights and input activations both to be float4 group-16, which
selects `CompressedTensorsW4A4Fp4`; this supports implementation, not an
endpoint result.

Interpretation: the inventory contains a cold B200 reservation but its state
is `maintenance` and expressly non-claimable pending director verification.
No provider API, SSH, claim, CUDA call, conversion, server, or scientific
sample was made. Actual project spend remains `$0.00`.

Next: after the director marks the listed B200 ready, launch one durable
shared-tool owner; run BF16 control then native-NVFP4 candidate, retaining the
claim for ordinary launcher/consumer repair and measuring complete requests.

## 2026-07-28 — retained-claim llmcompressor repair

Action: reused the finalized BF16 snapshot and pulled serving image; bound an
isolated `llmcompressor==0.12.0` producer manifest and tested its import. The
first overlay was rejected pre-science because it replaced the serving graph.
Repair-5 then reached conversion but found the removed `python -m
llmcompressor` entrypoint; repair-6 added a project-local compatibility shim
and reached the producer's real Gemma 4 load (1,188 tensors).

Evidence: no conversion manifest, control terminal, candidate terminal, CUDA
quantization marker, or endpoint request was persisted. Repair-6 stopped in
the producer's processor initialization because its isolated Transformers
Gemma 4 processor requires `torchvision`; the hash-bound retained-claim ready
generation is `b200-nvfp4-20260728T122126Z` (`7a4ca1a5…`). The full traceback
is retained at `artifacts/b200-nvfp4-endpoint-20260728t1052z/REPAIR_DIAGNOSTIC.txt`.

Interpretation: this is a recoverable producer-environment integration defect,
not a scientific result. The checkpoint, packet, serving image, and producer
manifest remain resident; no scientific submission was consumed.

## 2026-07-28 — offline producer V2 ready

Action: built the project-local closed producer bundle at `producer_v2/` with
`llmcompressor==0.12.0` and `torchvision==0.27.0`, an all-wheel SHA-256 lock,
and a compatibility adapter for the upstream `oneshot` entrypoint. Patched the
future owner to transfer only the lock, wheels, and adapter, then install them
into a separate producer venv with `--no-index`; it does not mutate the pinned
serving interpreter.

Evidence: a fresh isolated Python 3.12 environment passed `pip check`, the
adapter help path, and exact local config/processor smoke: `Gemma4Processor`
loaded without checkpoint weights. `B200_NVFP4_PRODUCER_V2_READY.json` is
SHA-256 `55c30003f36e30d4c3a0bda172f48cdda835905ab1a778d1acbb108a29793213`;
the final owner is SHA-256
`8c2bf95b03f34c57ae92a73247fc7c33478d586228a2a312cfd41b3b22b12b2a` and
passes `bash -n`.

Interpretation: the prior Gemma4Processor/torchvision defect has a reproducible
offline producer boundary. This cycle made no provider, bench, checkpoint,
conversion, endpoint, or scientific action; the project remains paused with
prior actual spend unchanged at `$6.7383062365694455`.

## 2026-07-28 — B200 V2 retained execution launch

Action: claimed the identity-verified B200 at `13:26:29Z` and launched the
controller-local owner. Its first cold staging pass exposed an impossible
self-hash check for `PACKET_MANIFEST.json`; this was a pre-science launcher
defect. The original owner retained the claim, a hash-bound repair request was
written, and repair-1 replaced only that packet-validation boundary under the
same claim.

Evidence: repair-1 PID `3150356` (start ticks `136134516`) is live, crossed
packet/calibration staging, and entered checkpoint reconciliation. No image
pull, CUDA conversion, control request, candidate request, or terminal exists
yet. The claimed B200 remains protected by the `16:19:08Z` watchdog.

Interpretation: no scientific sample was consumed. Continue the retained
owner through locked producer install, conversion, BF16 control, candidate,
terminal validation, and release; preserve the first repair diagnostic and
the continuous claim generation.

Update: repair-1 then exited pre-science from shell quoting in checkpoint
reconciliation, before any copy, CUDA, or request marker. Repair-2 (`3188699`
with start ticks `136376016`) is the immediate same-claim continuation with
that copy/verify command simplified; it is live and has re-entered checkpoint
reconciliation. The B200 claim timestamp remains `13:26:29Z`.

## 2026-07-28 — producer-install repair-3

Action: retained the B200 claim after repair-2's pre-science offline pip
bootstrap failure. Preserved `requirements.lock` and added the derived runtime
lock that removes only `pip==26.1.2`; the image-created venv supplies pip for
the remaining closed wheel install. The exact repair handshake request binds
both lock hashes and the replacement owner.

Evidence: repair-3 PID `3205966` (start ticks `136499939`) is live, has
crossed `producer_install_resume`, and is in `producer_stage`; no conversion,
control, candidate, or scientific request marker exists.

## 2026-07-28 — tokenizer-length repair-5

Action: repair-4 loaded the exact JSONL Dataset but hit the Gemma tokenizer's
unbounded `model_max_length` sentinel before calibration. Repair-5 binds an
explicit finite maximum to the same one-row Dataset, hashes the adapter and
owner, and resumes only native-NVFP4 conversion.

Evidence: repair-5 PID `3221455` / start ticks `136548263` crossed the adapter
installation boundary and has a live SSH child running the retained conversion.
The calibration SHA-256 remains `0a994e0d…`; no endpoint request or scientific
sample has started.

## 2026-07-28 — typed native-NVFP4 conversion incompatibility

Action: preserved repair-5's completed producer output and retrieved its
compact remote configuration rather than replaying conversion or either
endpoint arm.

Evidence: llmcompressor loaded all 1,188 tensors, tokenized the exact one-row
Dataset, wrote two shards, and dispatched 1,763 tensors. Its own immutable
consumer check then failed `missing_symmetric_float4_group16_w4a4`; the saved
config is BF16 and lacks a matching quantization config. The raw conversion
diagnostic and remote compact configuration are hash-bound in `TERMINAL.json`.

Interpretation: this is a decision-bearing producer incompatibility with the
required native-NVFP4 representation, not an endpoint sample. Control and
candidate remain unconsumed and must not be replayed under this submission.
