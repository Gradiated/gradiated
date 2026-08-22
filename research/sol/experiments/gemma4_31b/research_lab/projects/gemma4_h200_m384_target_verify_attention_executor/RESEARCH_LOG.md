# Research log

## 2026-07-30T09:29Z — source candidate and discriminator

Question: can the qualified c32 NGRAM M384 wave reuse request/page state inside
local and global attention without changing target semantics?

Action: traced the two bound predecessor artifacts into pinned SGLang
`28b095c0`, then followed `qkv_proj -> fused QKV RMSNorm -> RoPE ->
RadixAttention -> TritonAttnBackend.forward_extend -> o_proj`. Built a
request/KV-head schedule that flattens target-row × GQA-head into the
dot-product M tile, reuses each paged K/V tile across the GQA group, and folds
the future-KV store into the q-tile-zero CTA. Added an independent direct CPU
reference and a partition-capable online-softmax implementation.

Evidence:

- Source-backed: target metadata and masks are already built once per forward,
  not once per layer. Stock still launches one KV store and one attention
  kernel per layer, and maps attention by request/query-head.
- Analytical: a full wave has 1.750–1.760 TFLOP of attention work,
  38.360 GB compulsory unique prefix K/V, 145.815 GB stock logical K/V loads,
  and 120 stock store+attention launches. The candidate model has 61.392 GB
  logical K/V loads and 60 launches; stock grids are 1,024 CTAs (7.76 H200
  waves), while candidate local/global grids are 512/384 CTAs (3.88/2.91
  waves).
- Derived, not measured: the zero-cache peak-HBM byte-removal scale is
  20.454 ms/completed request, 3.272% of the locked 0.625149 s/request
  denominator. This is not a latency prediction or bound because stock L2
  reuse and attention critical-path time are unmeasured.
- Executed CPU oracle: three exact-head-count/head-dimension cases, including
  page permutation, branching tree mask, window clipping, and extremes, pass
  with max absolute error `3.33e-16`.
- Current official surfaces do not expose a proven drop-in for this exact
  tuple. Pinned Gemma4 excludes FlashInfer; FlashAttention's current d512 work
  is Blackwell-scoped; CUTLASS's paged low-latency GQA example is Blackwell;
  and none proves the pinned arbitrary NGRAM full mask plus d512 H200 path.

Interpretation: metadata reuse and direct FP8 KV are closed submechanisms—the
first already exists, and the second changes qualified BF16-cache semantics.
Grouped-head KV-tile reuse plus fused cache store remains a credible source
candidate, but no H200 performance or whole-request gain is claimed.

Next: only after positive spend/claim authority and an available H200,
materialize all admitted bytes under this project and execute
`H200_DISCRIMINATOR_CONTRACT.json`. Require bitwise attention, o-projection,
KV-cache, target-logit, acceptance, and completion equivalence before timing;
then measure L2/DRAM traffic, registers/spills, launches, component latency,
and a matched qualified endpoint.

## 2026-07-30T09:58Z — retained-claim producer-capture boundary

Question: can the admitted exact M384 component runner enter its first CUDA
call without fabricating Q/K/V?

Action: the live detached owner claimed the retained H200 and ran the staged
runner in the resident pinned SGLang image. It retrieved the worker terminal
and raw capture, then retained its heartbeat. A hash-bound repair request was
written for only the missing producer-capture stage.

Evidence: `REMOTE_TERMINAL.json` records
`recoverable_producer_capture_missing`, `cuda_invocation_started: false`, and
`science_consumed: false`. The project, base binding, amendment, and bench
state provide neither a capture manifest nor an authenticated acquisition
source. The owner acknowledged the request as
`repair_request_requires_director_rebind`; its loaded retry path cannot stage
or consume the requested capture, and the binding does not authorize owner
replacement.

Interpretation: this is an external-input/owner-entrypoint conflict, not a
kernel result or semantic negative. No synthetic Q/K/V, endpoint work, or
component measurement occurred.

Next: director must bind a provenance-addressed producer capture plus an
owner entrypoint that consumes it under the continuing claim, or explicitly
dispose the retained owner at its hard fence.

## 2026-07-30T10:01Z — repair-dispatch audit

Question: can the retained owner consume the bounded producer-capture repair
without replacing, releasing, or replaying the unconsumed component stage?

Action: inspected the decision-bearing remote terminal once, the live owner's
loaded retry entrypoint, and the existing repair records. Confirmed the owner
is live and the pool claim is heartbeating; no guest or provider state was
mutated.

Evidence: the runner's failure is pre-science (`science_consumed: false`,
`cuda_invocation_started: false`) because no provenance-addressed Gemma4
`qkv_proj -> fused RMSNorm -> RoPE` packet exists. The owner only hashes an
existing request and remains in
`repair_request_requires_director_rebind`; it cannot resume the requested
stage. The supplied `REPAIR_READY.json` is not a valid shared-handshake ready
contract: `repair-handshake status --root <project>` returns
`invalid_repair_ready_deadline`. Its existing request is preserved, not
overwritten, because it is already visible to the live owner and cannot be
made a new generation safely under this binding.

Interpretation: this is a typed repair-handshake/owner-retry-entrypoint plus
external producer-capture boundary, not scientific evidence. Patching the
on-disk owner cannot affect the live Python process, while replacement is
explicitly disallowed. No compliant in-place scientific retry exists.

Next: director rebind must supply an authenticated producer capture and a
live-owner-consumable retry entrypoint (or authorize a verified replacement)
before the retained claim's hard release fence.

## 2026-07-30T10:03Z — generation-1 repair dispatch remains unavailable

Question: can the existing claimed owner accept the requested bounded
producer-capture repair without replacement or replay?

Action: inspected the live owner's retry entrypoint, its persisted request,
the pre-science remote terminal, and the current atomic pool record once.

Evidence: PID `726791` remains live and heartbeating the original claim. Its
only request-present branch records
`repair_request_requires_director_rebind` and returns to its heartbeat loop;
it never archives/consumes the request or invokes the failed producer stage.
`REPAIR_REQUEST.json` already exists for generation
`m384-producer-capture-1`, and `REPAIR_READY.json` is rejected by the shared
helper as `invalid_repair_ready_deadline`. The retrieved terminal continues
to prove `cuda_invocation_started: false` and `science_consumed: false`.

Interpretation: the recoverable integration defect is the live owner's
missing retry dispatcher. With replacement expressly disallowed for this
operation, patching the project files cannot alter the already-running Python
owner and no compliant same-owner execution can be signaled. The existing
request is preserved; it is not overwritten or replayed.

Next: require a director-authorized replacement/adoption binding, or a live
owner entrypoint that consumes the existing request, before the hard release
fence.

## 2026-07-30T10:13Z — R2 adopted the original claim; producer acquisition is absent

Action: R2 wrote a dynamic standby marker after strict SSH verification and a
remote census found no generation-1 container or worker. The transition
re-read the original claim and PID `726791` / start ticks `152144312`, stopped
only that predecessor, and R2 adopted the original `09:57:05.800998Z` claim.

Evidence: `r2/R2_WORKER_CAPTURE.json` (SHA-256
`22f969a3848461c5a15a0a4178ff30c820739644ffedb816a2538a9852b9836b`)
records exit 127 before Docker or CUDA: `M384_MODEL_PATH_required`. The
earlier exact remote census also found no Docker image and no Gemma model
files, contradicting the inventory's resident-image assertion. R2 is live,
heartbeat is current, and no CUDA invocation or interpretable row exists.

Interpretation: this is a typed pre-science acquisition-contract defect, not
a component result. An authenticated local model acquisition path was never
provided and cannot be inferred without violating the no-synthetic-Q/K/V rule.

Next: retain the original claim under R2 until the hard fence. A successor
binding must supply the pinned model's local absolute path or authenticated
acquisition contract and reconcile the missing image, then retry only the
producer/consumer boundary.

## 2026-07-30T10:28Z — selective official-module producer acquisition passed offline

Action: replaced the full-checkpoint producer assumption with
`producer_acquisition/official_selective_producer.py`. It resolves the pinned
Hub revision, reads safetensors headers, range-fetches only layer 0 sliding and
layer 5 full-attention Q/K/(V), norms, and o-projection tensors plus embedding
rows 0..383, then directly constructs the official Gemma4 attention and RoPE
modules—never `AutoModelForCausalLM`.

Evidence: the blank project-local root has 642,714,624 bytes of hash-bound
selected tensors in `SELECTIVE_ACQUISITION_MANIFEST.json` (SHA-256
`7356b64c48602d8078b36c60baab3cb69848939944dbf97aa3174497ab42679a`).
`OFFICIAL_MODULE_EXERCISE.json` (SHA-256
`4e3f4d615b22aadb7ff9662c82d13305ecdda2ee6972dd92a33c381d33211d07`)
strictly loaded local/global official module state, exercised Q/K/V norms,
RoPE, and o_proj, and emitted the bound M384 local/global shapes. The first
selector mistakenly fetched the full embedding and did not reach modules; it
was removed, the selector narrowed to the 4 MiB prefix, and the preserved
attention ranges were reused through ordinary dtype, module-shape, RoPE-call,
and K=V repairs. The final run passed.

Interpretation: a reachable exact producer acquisition route exists without a
complete checkpoint, CUDA, a GPU claim, further provider action, or added
spend. This is support evidence only, not an attention sample or component
result. The exact SGLang cache/mask/stock-consumer capture still needs a new
authorized H200 binding.

Next: await that binding; stage only the immutable selective manifest and
bind it to the installed pinned SGLang producer/consumer.

## 2026-07-30T11:05Z — selective H200 attempt ended pre-CUDA

Action: the durable owner claimed the selective H200, pulled the pinned
SGLang image, and completed the remote revision-pinned selective acquisition
and official-module exercise. It then invoked the runner.

Evidence: the retrieved remote manifest has the bound SHA-256
`7356b64c48602d8078b36c60baab3cb69848939944dbf97aa3174497ab42679a` and
the remote module exercise is retained. Runner stderr proves it failed before
CUDA opening nonexistent `/work/stage/producer_packet.json`; no science marker,
candidate submission, CUDA invocation, or decision-bearing ledger exists.
The owner released the claim to maintenance after its terminal retrieval path
failed; `SELECTIVE_H200_ATTEMPT_TERMINAL.json` preserves the diagnostics.

Interpretation: this is a recoverable producer-packet/runner integration
defect, not a semantic or performance result. The selective producer stage is
durable and must be reused. The conservative cumulative exposure through the
already-scheduled watchdog cleanup is $4.880629836541667.

Next: require director re-admission because a researcher may not re-ready the
maintenance bench. Repair only the runner's construction of the actual
installed-SGLang producer packet and stock consumer boundary.
