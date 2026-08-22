# Research log

## 2026-07-29 — offline preclaim packet

Question: can one RunPod RTX PRO 6000 Blackwell (`sm_120`) run the exact stock
Gemma 4 31B dynamic-FP8 concurrent-c32 endpoint within the bound economic
ceiling?

Action: materialized the director-bound tokenizer/configuration, c32 identity,
and 32 exact payloads under this project as read-only hard-linked bytes, then
produced a hash-bound JSONL schedule and a lifecycle-pure retained-claim owner.
The owner uses `lab-endpoint-pair` in single-arm mode at concurrency 32, so it
does not create an unintended second 32-request comparator submission.

Evidence: exact tokenizer, c32 identity, and payload digests match the
admission binding. `test_science_endpoint_pair.py` passed (8 tests), and the
owner's hash-bound preclaim validation passed. No bench was present or claimed;
provider exposure is `$0.00`.

Next move: after the director makes the `$14` reservation durable, register a
fresh RunPod `sm_120` bench and supply its unexpired lifecycle binding to the
detached controller command in the PRECLAIM terminal.

## 2026-07-29 — Workstation SSH-port preclaim repair

Action: replaced only the obsolete Server literal in the later-execution owner
with the director-verified Workstation accelerator and made `ssh_port` a
required integer emitted as distinct `ssh`, `-p`, `40070` argv entries. The
original immutable execution packet remains bound as `f7c932bb…`; a separate
runtime manifest binds the repaired owner instead of rewriting scientific
packet bytes.

Interpretation: this clears the local lifecycle defect but does not authorize
a claim or any remote operation. The one exact c32 sample remains unconsumed.

## 2026-07-29 — retained-claim remote argv repair

The pre-science stage failure was `mkdir: missing operand`: `ssh` had joined
separate `bash`, `-lc`, and script arguments, so bash received only `mkdir`.
The owner now sends one quoted `bash -lc` command string while retaining strict
SSH and port `40070` as distinct local argv. The offline argv fixture is
`artifacts/rtxpro6000-fp8-endpoint-20260729t0338z/REMOTE_ARGV_REPAIR_FIXTURE.json`.
The first corrected remote preparation passed and the durable retained-claim
owner began the first manifest-listed shard transfer. No endpoint request or
science-start marker has been issued.

## 2026-07-29 — retained CUDA-graph disable reload

Action: bound repair request `repair-1785298520` to director reload binding
`e6402f2e…`, then replaced only the authorized repair-3 controller after it
accepted the request. Repair-4 (`PID 3895570`, start ticks `141496386`) retains
the original 03:41:40Z claim and starts the prepared `--disable-cuda-graph`
owner without restaging weights or broadly reinstalling runtime packages.

Evidence: owner `ee8ee282…`, runtime manifest `6cbb4e29…`, stage terminal
`d0a64c9d…`, and runtime-import terminal `4f857701…` matched their binding.
The exact c32 endpoint sample remains unsubmitted.

## 2026-07-29 — pre-science memory and RoPE repairs

Repair-4 cleared CUDA-graph capture but exposed a server-load OOM; repair-5
lowered only `mem_fraction_static` to 0.70 and then reached SGLang fused-RoPE
execution. That exact production path failed before HTTP because its JIT
generated `compute_120f` for CUDA 12.8 NVCC. No science marker, endpoint
terminal, or request output exists. A newer director binding `faa3fc62…` now
requires an exact source-level RoPE producer/consumer oracle before retry.

## 2026-07-29 — exact sm_120 installed-source RoPE fallback

Question: can the retained SGLang 0.5.16 production RoPE consumer execute the
exact Gemma 4 shape on sm_120 without changing model semantics?

Action: routed only capability-major 12 through SGLang's installed
`RotaryEmbedding.forward_native`; pinned Gemma source proves fused KV storage
is disabled and passes `None`. Added a package-layout compatibility symlink
from the owner's obsolete NVCC lookup to the wheel-recorded CUDA 13.0.88
binary. No package install, model restage, HTTP request, or owner replacement
occurred.

Evidence: `SM120_ROPE_JIT_SOURCE_FALLBACK.json` (`d3acb55b…`) records pre/post
source hashes and one no-HTTP 8,192-token BF16 call: q `[8192,8192]`, k
`[8192,4096]`, finite, identical strides, max absolute and relative-L2 error
both zero against the official native reference. The first standalone
constructor attempt stopped before CUDA because global server args were absent;
its preserved invalid-attempt artifact binds the narrow amendment. Request
`7277977e…` was published for `repair-1785299364` at `04:43:25Z`; owner PID
`3898656` crossed the unchanged CUDA-13 guard and launched fresh server PID
`12087` at `04:43:32Z`.

Next move: let the durable owner proceed from model health into the sole
unconsumed concurrent-c32 endpoint sample; do not replay the RoPE oracle or
duplicate the server.

## 2026-07-29 — retained source repairs and sole c32 terminal

The retained owner exposed a CUDA-toolchain mismatch rather than an RoPE
semantic failure: installed NVVM 13.3 emitted PTX 9.3 while the bound CUDA
13.0.88 `ptxas` accepted at most PTX 9.0. Without reinstalling, the repair
routed only sm_120 GELU-and-multiply and clamp-position calls through their
installed official framework equivalents. Exact target-GPU BF16 activation
and int64 clamp oracles passed, and server PID 16036 reached health with
`--disable-cuda-graph` and `mem_fraction_static=0.70`.

The public RunPod HTTP mapping then timed out before any response. The first
SSH-tunnel amendment reached `/` and preserved 32 HTTP-405 rows; the next
reached native `/generate` and preserved 32 structured pre-generation schema
errors. Neither produced token output or a decision-bearing sample. The final
adapter changed only the route to installed `/v1/completions`, retaining the
original URL hash, request bodies, packet, checkpoint, and c32 schedule.

Measured result: 32/32 requests completed with nonempty outputs, 4,214 prompt
tokens and 358 completion tokens each. The 71.482293-second run is
`2.23382165625 s/request`, 113.02% above the
`1.048637203302411 s/request` price-normalized ceiling. At the `$1.55/GPU-hour`
planning rate this is `$0.210364/M` total tokens at theoretical full
utilization and `$0.233738/M` at 90%. Terminal `c79a2f6…` and pair run
`47d62e6…` are canonical; the sole sample is consumed. The unchanged owner
released the original claim to maintenance at `05:12:46Z` and exited.

Decision: close this exact RTX PRO 6000 Workstation Edition, SGLang 0.5.16,
stock dynamic-FP8 configuration as price-normalized negative. Do not transfer
the result to the unavailable Server Edition. Conservative project exposure
is `$9.45`, covering the full director-bound provider lifecycle through its
still-active cleanup watchdog.

## 2026-07-29 — corrected-input reclaim revoked

New director binding `DIRECTOR_RTXPRO6000_CORRECTED_INPUT_RECLAIM_REVOKED_20260729T0523Z.json`
(`ad329242…`) superseded the earlier `c59a2c91…` correction request: the
predecessor had misattributed archived application-error evidence, while the
hash-bound `c79a2f6…` terminal already contains 32 successful generated
responses. The stock endpoint remains a measured negative and cannot be
replayed.

The stale local owner was cancelled after launch. Its incomplete local run is
preserved only as `artifacts/rtxpro6000-corrected-input-20260729t0523z/REVOKED_LATE_OWNER_CANCELLATION.json`
(`05732b1f…`): 11 rows completed before cancellation, so it is neither an
accepted sample nor a new project terminal. The exact local controller and
SSH tunnel are absent; a cross-namespace census shows no endpoint driver and
the resident SGLang PID 16036 plus scheduler PID 16233 remain healthy. The
bench is in director maintenance and project exposure remains `$9.45`.
