# Research log

No research result yet. The director admitted this independent zero-GPU lane
after the QKV-mainloop cluster-handoff and bounded-recomputation families
closed analytically.

## 2026-07-30 — selected row-owned two-phase finalizer

- **Question:** Can the exact TP=1 down-projection boundary avoid global
  materialization through the next dynamic-E4M3 QKV input without changing
  either BF16 rounding boundary?
- **Action:** Traced pinned SGLang `28b095c…` from the `[M,21504]` dynamic-FP8
  down GEMM through post-FF RMSNorm, residual/scalar, the next layer's input
  RMSNorm, small-batch E4M3 producer, and `[5376,16384]` QKV consumer. Built a
  source candidate, deterministic fragment oracle, three-way SM90a physical
  comparison, and an unfunded exact-consumer H200 A/B contract. The first
  local oracle import lacked NumPy; `ORACLE_ATTEMPT_1_INVALID.json` records the
  unchanged dependency-free amendment and the valid retry.
- **Evidence:** [CPU/reference] All 147 rows at M=1/16/32 across random,
  signed-zero, and extreme fixtures match bitwise for the required residual
  BF16, registered next-normalized BF16, FP32 scale, complete E4M3 bytes,
  aligned partial tree, and eight Q/K/V-spanning consumer fragments.
  [Analytical] The selected one-CTA-per-row finalizer uses 43,520 bytes shared,
  duplicates zero down FLOPs, saves 43,008 intermediate bytes per row, and
  replaces three post-down producer launches with one. The epilogue-partial
  path adds 672 bytes/row and producer work, so it is dominated. An eight-CTA
  DSM cluster covers only 512 of 5,376 columns; 11 clusters cannot share a
  portable barrier/address space, while serializing one cluster creates 11
  producer tile slots. [Measured, transfer-limited] The older exact-runtime
  trace assigns a loose 0.607% whole-request ceiling to the entire affected
  kernel families; its M=118/1409/1631/2048 mix does not predict M<=32 timing.
- **Interpretation:** `row_owned_two_phase_finalizer` is the only promoted
  source decomposition. It keeps the tuned down GEMM and materialized BF16
  down output, but holds both later BF16 rows in shared memory, persists only
  the next-layer residual, and emits the unchanged QKV consumer ABI. This is
  decision-ready for a cheap H200 component, not a bench or endpoint claim.
- **Next:** If the director funds a later H200 component, execute
  `H200_EXACT_CONSUMER_CONTRACT.json`; first prove complete bytes and the
  candidate symbol at M=1, then collect alternating M=1/16/32 boundary and
  down-to-QKV timings. Keep TP!=1 on stock and do not infer endpoint gain.

## 2026-07-30 — H200 attempt invalid before CUDA submission

- **Action:** Claimed `h200-downproj-computeinstance-e00qft1sf416qp6knw` at
  `09:13:31.913396Z` under a durable `GpuClaimSession` owner, pulled the exact
  pinned image, and invoked the narrow extension build.
- **Evidence [measured]:** The image pull completed at the bound digest. The
  extension compilation then failed at `09:24:53Z`: the pinned torch headers
  do not export `at::cuda::getDefaultCUDAStream`. The preserved
  `H200_COMPONENT_TERMINAL.json` has `candidate_cuda_started=false`,
  `science_started=false`, and zero rows; raw compiler evidence is in
  `artifacts/h200-downproj-20260730t0913z/remote_terminal.json` and
  `remote.stdout`.
- **Interpretation:** This is a recoverable pre-science stream-API integration
  defect, not a negative mechanism result and not a consumed component sample.
  The owner released the healthy bench to maintenance, so this project must not
  re-ready or reclaim it. The conservative full registered lifecycle cost is
  `$2.8583333333` (4,200 s at `$2.45/h`), leaving `$0.1416666667`.
- **Next:** Director must decide whether to re-ready/rebind a repair venue and
  authorize sufficient additional spend. The only permitted repair is the
  narrow CUDA-stream API wrapper; no ledger may be replayed as a second sample.
