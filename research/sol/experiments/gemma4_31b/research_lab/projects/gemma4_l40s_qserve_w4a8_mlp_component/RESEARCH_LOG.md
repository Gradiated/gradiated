# Research log

## 2026-07-24 — fixed SM89 QServe W4A8 packet ready

- Question: can QServe progressive group-128 W4A8 replace the measured resource-heavy Marlin decode MLP schedule on L40S?
- Action: pinned OmniServe/QServe `02b2925aa6fa3b92b06316a1524b7f38922cd9c8`; bound its SM89-supported low-M `32x64x128`, four-warp, three-stage GEMM; implemented the exact checkpoint-free Gemma gate/up–tanh-GELU-and-quant–down chain, independent dequantized-W4 oracle, and actual SGLang online-FP8 control.
- Evidence: `MECHANISM_BINDING.json` and immutable `GPU_INPUT_MANIFEST.json`. The executed GEMM differs from the pinned upstream bytes only by removing four trailing spaces. Local AST/JSON/shell/hash checks and DevEx checks pass. The fixed source schedule uses 24,960 dynamic shared-memory bytes and 128 threads; exact grids are 672 gate/up blocks (4.7324 L40S waves) and 84 down blocks (0.5915 waves). Compulsory W4 weight bytes are 173,408,256 versus 346,816,512 for FP8.
- Interpretation: the gate/up path should escape Marlin's measured 200-register, 233,472-byte, one-wave collapse; down remains grid-underfilled and is the main falsifier. Registers, spills, numerical correctness, and warm latency remain target-GPU measurements, not offline claims.
- Next: the director should provision and register one L40S bench from `PROVIDER_REQUEST.json`. Claim it only after registration, then run the immutable packet once and retain compile resources, all eight correctness/timing rows, and candidate-path evidence.

## 2026-07-24 — pre-science pinned-runtime capacity blocker

- Action: atomically claimed `l40s-qserve-e00a74kcbps8v00fk4`; verified L40S SM89 identity and copied the manifest-bound project snapshot. The prescribed host compile was attempted once.
- Evidence: host compile failed before import with `ModuleNotFoundError: torch`; host also had no `nvcc` or `sglang`. The pinned SGLang image pull then filled the 40-GiB filesystem to 100% without creating an image. The incomplete pull was removed, 22 GiB recovered, and the bench released to maintenance. Remote output and state are in `artifacts/l40s-qserve-20260724t0233z/` (archive SHA256 `f797ea967e2d0d054d8ff4738e3ad88df81ed90ed72b1f6050882f703fc8fd66`).
- Interpretation: this is a typed pre-science environment-capacity blocker, not a candidate result; `REMOTE_INVOCATION_INTENT.txt` exists but no candidate CUDA, control workload, request row, or scientific terminal exists.
- Next: director must supply a larger-disk or preloaded-image compatible L40S bench, then rerun the same immutable packet without replaying any scientific arm.

## 2026-07-24 — immutable L40S component result

- Action: after the director's in-place disk repair, grew the guest root to 145 GiB, pulled the exact pinned SGLang image, compiled the unchanged SM89 extension, and ran the one immutable profiler-off component packet.
- Evidence: compile passed with SM89 gencode and ptxas register counts up to 162. Candidate CUDA/science markers are true; all eight production M rows persisted and passed candidate-vs-dequantized-W4 correctness (relative L2 0.00053–0.00097, cosine/finite checks passed) and candidate-path audit. Candidate p50 was 0.2847–0.2974 ms versus control 0.5321–0.5496 ms, speedup 1.84–1.89x. Boundary rows were finite for zero and negative-extreme, but positive-extreme output was nonfinite (`output_sum_squares: Infinity`). Full terminal and raw output: `artifacts/l40s-qserve-20260724t0233z/final-output/component/TERMINAL.json` and `final-remote-output.tar.gz` (SHA256 `d4c07adbfe6e502da2be00fdad16e20445379fa40db309fcdf034d799b837824`).
- Interpretation: the fixed QServe-style schedule is a component reject despite strong production-shape speed and numerical agreement; the preregistered finite-output boundary closes this schedule. The candidate path was executed, so no replay, representation sweep, or endpoint continuation is authorized.
- Next: release the healthy unoccupied L40S ready while retaining the pinned image and compiled cache for director review.

## 2026-07-24 — director admits one BF16-range continuation

- Decision: the consumed FP16-output schedule stays closed. The isolated
  positive-extreme nonfinite row, eight correct production rows, and measured
  1.84–1.89x speedup support one materially different BF16-output epilogue
  mechanism under `BF16_EPILOGUE_CONTINUATION.json`.
- Scope: preserve group-128 W4A8, INT8 activations, scales, and the fixed SM89
  schedule. Change only both GEMM output epilogues and the adjacent
  activation-quant dtype contract needed to keep BF16 range. Clipping,
  fallback, tile/format sweeps, and Marlin replay are prohibited.
- Gates: run the three boundary rows first, then the eight production rows only
  on a boundary pass, then stage the exact checkpoint and run one coherence
  smoke plus c32 endpoint only on a correct positive component.
- Economics: at committed planning rates, the L40S price-normalized endpoint
  ceiling is `1.8853265455 s/request`. A passing endpoint nominates later
  GPQA-Diamond/TauBench; no quality evidence transfers from FP8.
- Resource: reuse only `l40s-qserve-e00a74kcbps8v00fk4` through `08:15Z` under
  renewed `$14` authority and its existing `08:30:59Z` cleanup watchdog.

## 2026-07-24 — BF16 component positive, exact endpoint rejected

- Decision: consume the single BF16-output continuation on the retained L40S.
  Both GEMM epilogues now write BF16, and the adjacent fused GELU/activation
  quantizer reads BF16; group-128 W4A8, INT8 activations, scales, and the fixed
  SM89 schedule are unchanged.
- Measured component evidence: all three boundary rows passed. The prior
  positive-extreme failure is finite at an absolute maximum of `104960` and an
  FP64-consumed sum of squares of `23878595969024`. All eight production rows
  (`M=1,2,4,8,12,16,24,32`) passed candidate-path and dequantized-W4
  correctness. Candidate speedup over the actual online-FP8 control was
  `1.8706–1.9241x`; the M32 call-weighted bound saves `0.174605 s/request`.
  The terminal is
  `artifacts/l40s-qserve-bf16-20260724t0358z/retrieved/component/TERMINAL.json`.
- Exact producer: materialized and rehashed
  `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`
  (`62,578,655,208` bytes), transferred it resumably, and produced 180
  content-addressed W4/FP8 cache shards once. The server loaded the exact
  checkpoint, captured CUDA graphs through c32, passed its model probe, and
  remained healthy with zero restarts.
- Endpoint evidence: all three real coherence requests reached the loaded
  endpoint and observed the BF16 candidate decode path (`120` candidate path
  events). Responses degenerated into repeated `B`/`H` tokens, so coherence
  passed `0/3`. This is a scientific `endpoint_reject`, not a retryable
  launcher failure. The single c32 workload did not start because the
  coherence gate failed. Terminal and immutable-cache manifest:
  `artifacts/l40s-qserve-bf16-20260724t0358z/endpoint-retrieved/artifacts/bf16-qserve-c32/ENDPOINT_TERMINAL.json`
  and `W4_REPRESENTATION_MANIFEST.json`.
- Resource/economics: cumulative conservative project exposure is
  `$1.6504614233` (`$0.5507686080` prior plus `$1.0996928153` from the
  `04:00:13Z–05:16:40Z` retained claim), below the `$14` cap. Released only
  `l40s-qserve-e00a74kcbps8v00fk4` to maintenance. The healthy
  `gemma-qserve-bf16-endpoint` container, exact checkpoint, compiled extension,
  and immutable 180-file cache remain resident for director disposition; the
  consumed coherence arm must not be replayed.

## 2026-07-24 — director admits one causal real-weight discriminator

- Evidence: the kernel remains correct against its dequantized-W4 oracle, while
  the exact 180-file cache records about 12–13% reconstruction error per real
  shard and the all-layer endpoint collapsed on 3/3 prompts.
- Decision: reactivate this same project for
  `REAL_WEIGHT_CAUSAL_DISCRIMINATOR.json`, using fixed W4-prefix depths and one
  first-divergent-layer oracle comparison on the resident L40S.
- Stop rule: a fused-oracle match plus cumulative degradation closes
  uncalibrated W4. Only a proven discrete mapping/order/scale/routing defect
  permits one repair, new held-out coherence, and conditional c32.
- Limits: cumulative project authority `$6`, existing bench only, through
  `08:15Z`; no representation or schedule sweep and no consumed-prompt replay.

## 2026-07-24 — causal trace closes uncalibrated all-layer W4

- Action: claimed only `l40s-qserve-e00a74kcbps8v00fk4` and ran the fixed
  real-weight prefix depths `0,1,15,30,45,60` against the resident exact
  checkpoint, 180-file W4/FP8 cache, and BF16 SM89 extension. A depth-0
  control-prefill failure mechanically proved the cached FP8 B operand had
  lost its required column-major stride; the single allowed routing/layout
  repair restored that stride without regenerating weights or replaying a W4
  candidate path.
- Measured trace: depth 0 returned exactly `cobalt:17` with `420` FP8 layer
  calls. Depth 1 first diverged at layer 0/output-token index 2 while retaining
  the visible text; its audit was `8` W4 plus `472` FP8 calls. Depths 15, 30,
  45, and 60 all diverged at token 0 and reached the 32-token length cap with
  increasingly degenerate text. Their exact W4/FP8 counts were
  `495/1485`, `990/990`, `1485/495`, and `1980/0`.
- First-divergent-layer oracle: on the real layer-0, forward-step-2 hidden
  state, fused W4 versus the dequantized-W4 oracle was finite with relative L2
  `7.67e-6` at gate/up and `0` at activation and down (cosine `1.0`). The
  dequantized-W4 oracle versus cached FP8 was `4.23%` at gate/up, `11.93%`
  after activation, and `15.42%` at down. A corrected capture reproduced the
  common two-token prefix but not the original depth-1 token insertion; this
  residual nondeterminism is retained and does not authorize a second repair.
- Decision: terminal
  `artifacts/l40s-qserve-causal-20260724t0546z/retrieved-final/TERMINAL.json`
  classifies `uncalibrated_w4_representation_reject`. The fused kernel follows
  the lossy representation; cumulative real-weight error, not a fused packing
  mismatch, explains the endpoint collapse. Held-out coherence and c32 did not
  start.
- Resource/economics: complete evidence was retrieved before release. The
  claim lasted `3822.741 s` and cost `$0.9163782416`; cumulative conservative
  project exposure is `$2.5668396649`, below the `$6` ceiling. The healthy
  trace-enabled server, exact checkpoint, W4 cache, and compiled extension
  remain resident, and the bench was released to maintenance for director
  disposition.
