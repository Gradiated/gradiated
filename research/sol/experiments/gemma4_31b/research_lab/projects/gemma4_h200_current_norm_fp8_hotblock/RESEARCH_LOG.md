# Research log

## 2026-07-29 — director admission

Admitted as a zero-GPU deep mechanism lane independent of streamed global KV.
The immediate output must be working exact-shape source plus an oracle and
target runner, or a typed causal falsification—not another readiness packet.

## 2026-07-29 — decode-only RMSNorm-to-FP8 candidate

- **Question:** Can the exact current pre-attention input RMSNorm feed dynamic
  E4M3 QKV directly without repeating the prior residual semantics failure or
  prefill regression?
- **Action:** Mechanically bound the v10 model/image/workload, traced the
  single-consumer `input_layernorm -> qkv_proj -> per-token quant ->
  fp8_scaled_mm` path, and implemented an sm90a producer, decode-only runtime
  adapter, CPU oracle, and real-weight H200 runner. `M>32` remains stock.
- **Evidence:** [Measured locally] the pure-CPU exact-shape/edge oracle passes;
  M=32 dequantized relative L2 is `0.00284797` under the finite `0.003`
  retained-H200-derived tolerance, with no nonfinites. [Previously measured on
  the identical pinned H200 stack] the clean M=32 QKV component improved
  `0.058224 -> 0.050144 ms` with consumer relative L2 `0.00092547`.
  [Derived] one launch and 688,128 logical global bytes disappear per
  layer-call; over 60 layers and 358 fixed c32 decode steps the conservative
  historical-component projection is `0.0054237 s/request` (0.868%).
- **Interpretation:** The decode-only plain path survives for one fresh target
  component run. Residual-fed fusion remains semantically falsified and
  M=2048 prefill remains physically falsified. No GPU, CUDA, pool, SSH,
  provider, paid spend, or streaming-project mutation occurred.
- **Next:** Only after director authorization, materialize the exact four
  layer-0 component tensors under this project and run `h200_runner.py` once in
  the pinned image; require the complete row ledger and graph proof.

## 2026-07-29 — exact layer-0 component materialized offline

- **Question/action:** Can the four director-bound layer-0 norm/Q/K/V tensors
  be isolated exactly without touching the competing H200 lane? Used
  `materialize_component.py` with `safetensors.safe_open` on the bound source
  shard, writing only `inputs/gemma4-layer0-norm-qkv-component.safetensors`.
- **Measured evidence:** The source shard identity matched
  `eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa` and
  checkpoint manifest matched
  `6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6`.
  The finalized component is 176,172,392 bytes with SHA-256
  `dfa05dcf1f3f9ad6dd40f5318cf6c2c6d55eb93beebf0239f205e7fa88b85829`.
  It contains exactly four bfloat16 tensors: norm `[5376]`, Q `[8192,5376]`,
  K `[4096,5376]`, and V `[4096,5376]`; each value hash was verified before
  and after atomic finalization.
- **Checks:** `h200_runner.py --describe` parsed successfully for the bound
  H200/M=32 geometry and three-row ledger. No GPU, CUDA, pool, SSH, provider,
  or streaming-project operation occurred; no scientific sample was consumed.
- **Interpretation/next:** This is an executable offline component handoff,
  not H200 measurement. A later director must issue a separate positive-spend
  binding before the exact H200 component run.

## 2026-07-29 — exact H200 M=1/16/32 component result

- **Binding/lifecycle:** Read and verified
  `DIRECTOR_NORM_FP8_HOTBLOCK_H200_COMPONENT_EXECUTION_20260729T1557Z.json`
  (SHA-256 `d16a879198c48697ef4eb5a6ac2859f7b44965c5550be5388809e5ec309178bf`).
  Claimed the named H200 at `2026-07-29T16:03:04.798159Z`, reused the pinned
  image/checkpoint/cache state, and released the exact generation at
  `2026-07-29T16:08:47.213448Z`. Exposure was 342.415 seconds, conservatively
  `$0.234`, below the cumulative `$2.00` reservation.
- **Execution:** The first two attempts were ordinary pre-science launcher
  defects (pre-created output directory, then missing `inputs/` component
  path); both preserved typed `science_started:false` evidence and were not
  counted as samples. The corrected pinned-image invocation ran exactly once
  through the scientific path with the four hash-bound staged files.
- **Measured result:** Retrieved
  `artifacts/norm-fp8-h200-component-20260729t1557z/TERMINAL.json` (SHA-256
  `42cdb4854b0710a0afc3a92d6eb52c6209cd28b6fca48ef3cc732f1b37a5c10b`). The
  complete M=1/16/32 ledger and CUDA graph proof passed structurally; graph
  replay versus direct output had relative L2 `0.0`. Numerical equivalence
  passed at M=1, but failed at M=16 (`consumer relative L2 0.00225347`) and
  M=32 (`0.00231768`) against the `0.002` gate. Both had cosine about
  `0.999997`, zero nonfinites, and full output consumption.
- **Timing:** Candidate component medians were `0.050912 ms` (M=1),
  `0.049840 ms` (M=16), and `0.049856 ms` (M=32). M=32 timing was positive
  versus the `0.058608 ms` baseline component, but the candidate is rejected
  for this exact semantics contract because M=16/32 numerical gates fail.
- **Interpretation/next:** Classify this exact decode norm-to-dynamic-E4M3
  QKV component as `component_negative`; preserve the timing and graph
  evidence, do not promote it to endpoint use, and redirect the next slot.
  Guest GPU returned to 0 MiB with no container left running.

## 2026-07-30 — exact-order causal repair

- **Question/action:** Reopened only the rejected pre-attention
  RMSNorm-to-dynamic-E4M3 source at zero GPU. Traced the exact pinned
  FlashInfer RMSNorm and SGL quantizer, simulated stock/rejected/corrected
  intermediates for M=1/16/32, then implemented a new exact-order source and
  strengthened the retained H200 runner to require activation, FP32-scale,
  and real-consumer byte identity.
- **Evidence:** [Source-backed] the first divergence is the rejected source's
  256-thread scalar-strided/down-shuffle FP32 square sum versus stock's
  672-thread contiguous-vec8/two-level-XOR sum. [Measured CPU] all 147 rows
  across exact layer-0 loaded norm weight/random activation, adversarial
  finite dynamic range, and signed-zero families match corrected versus stock
  square-sum, BF16 normalized, E4M3 activation, and FP32 scale bytes; the
  E4M3 encoder matches pinned Torch on 380/380 probes. [Measured compiler]
  exact-image sm90a compile/load passes with 32 registers/thread, 10,880 B
  shared memory, and zero spills.
- **Interpretation:** Publish `source_complete_exact_candidate`. The source
  retains one-launch and 688,128 logical global-byte elimination at M=32 but
  uses 672 threads/CTA, so rejected-source timing does not transfer. A later
  H200 run must re-establish exact bytes and contemporaneous real-QKV timing.
  No GPU, bench, SSH, provider mutation, CUDA kernel invocation, new spend, or
  rejected-source replay occurred.
- **Next:** Director may nominate one hash-bound H200 M=1/16/32
  exact-consumer falsifier under fresh positive spend authority; otherwise
  this zero-GPU cycle is complete.

## 2026-07-30 — owner-control and final-identity repair

- **Action:** Repaired only the director-named owner and claim-launch files.
  The owner now declares adoption after generation validation and heartbeat
  start, before immutable staging; recoverable phases wait for, consume, and
  re-enter their exact repair generation; and release is fenced to one exact
  claim generation. The launcher releases only a pre-adoption failed claim.
- **Evidence:** [Measured offline] Python compilation and all five required
  deterministic fault injections pass in `OWNER_CONTROL_FAULT_INJECTIONS.json`
  (`2d2acc97...`). Current `MECHANISM_REPAIR_TERMINAL.json` hashes to
  `b1d8254e...`, which is now the owner input identity. No claim, SSH, CUDA,
  science, staging, image pull, R5 inspection, or provider mutation occurred.
- **Interpretation/next:** `NORM_FP8_OWNER_CONTROL_READY.json` is a
  claim-disabled readiness terminal only; it does not consume or promote the
  component. A later director must issue a fresh execution clock before any
  H200 action.

## 2026-07-30 — retained-claim launcher repair boundary

- **Action/evidence:** The bound owner staged all six immutable inputs, then
  its container command exited before invocation with `../worker.stdout:
  Permission denied`. Remote capture confirms no invocation marker, terminal,
  rows, worker output, or CUDA evidence. The documented generation-0
  retrieval request was consumed exactly once and reproduced only the missing
  terminal, proving generation-1 cannot reach the actual launcher fault.
- **Interpretation/next:** This is a pre-science owner-repair-entrypoint
  conflict, not a component sample. The live owner retains the same claim;
  only a director-bound same-claim transition or amended dispatcher may resume
  `scientific_runner` with a writable output path.

## 2026-07-30 — R2 transition: pre-science cache permission boundary

- **Action:** Bound and launched the director-authorized R2 transition under
  the original `07:57:09Z` claim. A self-matching remote census was repaired
  once in place; the corrected host-side worker capture then reached the
  pinned runner process.
- **Evidence:** `worker-r2.stderr` (`d364130d...`) shows FlashInfer failed
  importing before identity validation because non-root execution tried to
  create `/.cache`. The recovered `INVOCATION_STATE.json` (`81451c76...`)
  records `science_started:false`, zero completed rows, and no first call.
  There is no terminal or decision-bearing component result.
- **Interpretation/next:** This is a second localized pre-science integration
  failure after the single immediate R2 retry, not a consumed sample. The
  dead R2 owner and retained claim require deliberate director recovery; do
  not replay the component or infer a scientific terminal from the exit.
