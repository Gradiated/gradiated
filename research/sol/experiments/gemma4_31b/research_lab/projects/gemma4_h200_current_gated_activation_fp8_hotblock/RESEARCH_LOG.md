# Research log

## 2026-07-29 — exact decode gated-activation/FP8 candidate

- Question: Can Gemma 4's decode `GeluAndMul` output be quantized to dynamic
  E4M3 in the activation producer and passed directly to the unchanged
  layer-0 down-projection consumer?
- Action: Traced the pinned Gemma 4 alias to `Gemma3MLP`, the exact
  `gelu_pytorch_tanh` CUDA activation, `Fp8LinearMethod.apply`,
  `sglang_per_token_quant_fp8`, and `fp8_scaled_mm`. Implemented an
  sm90a-only fused producer, decode/TP1 runtime adapter, pure-CPU oracle, and
  real-weight H200 runner with M=1/16/32 and CUDA-graph contracts.
- Evidence: `CPU_ORACLE_RESULT.json` passes random M=1/16/32 and zero, tiny,
  and extreme rows. The exact one-round BF16 candidate matches the source
  semantics and quantized values exactly in the analytical oracle. A nearby
  two-round formulation is falsified: at M=32 it changes 27.46% of BF16
  activation values, 1.67% of FP8 values, and has 0.801% dequantized
  relative-L2 error.
- Interpretation: The boundary is source-complete and remains eligible for
  one later exact-H200 component run. At M=32 it removes one launch,
  2,752,512 contractual logical producer/consumer bytes, and 4,128,768
  source-level global load/store bytes per layer call; actual HBM savings may
  be smaller because the 1.3125-MiB activated tensor fits in H200 L2.
- Next: Materialize the exact layer-0 BF16 down-projection tensor and its
  hash manifest under this project before any future claim, then run
  `h200_runner.py` once in the pinned SGLang image. Target CUDA was
  intentionally not executed in this zero-GPU turn.

## 2026-07-29 — bound layer-0 component materialized offline

- Question/action: Can the admitted source-complete candidate receive its one
  exact real-weight component without touching the shared H200 lane? Read the
  director binding once; extracted only
  `model.language_model.layers.0.mlp.down_proj.weight` from the bound shard.
- Evidence (measured): Source shard size and SHA-256 matched the checkpoint
  manifest; index mapping selected `model-00001-of-00002.safetensors`.
  The temporary safetensors was atomically finalized as a 231,211,144-byte
  project-local file containing exactly one BF16 tensor of shape
  `[5376, 21504]`. Reopening the final file proved exact source payload
  equality; component SHA-256 is recorded in the component manifest.
- Evidence (measured): `python3 h200_runner.py --describe` parsed the
  unchanged runner contract, including the exact key, BF16 shape, H200
  geometry, CUDA-graph arms, and checkpoint-manifest identity. No GPU, CUDA,
  pool, SSH, provider API, Docker, or spend was used.
- Interpretation/next move: The component prerequisite is complete and
  executable for a later director-authorized H200 component run. Pause this
  project and keep it non-claimable; no scientific sample was consumed.

## 2026-07-29 — H200 execution binding stopped pre-science

- Question/action: Execute the single bound M=1/16/32 component ledger on the
  named warm H200 under binding `8a5bd494...`. Verified the binding, all nine
  immutable input hashes, the `$2.00` cumulative reservation, zero prior
  spend, available bench, watchdog, and exact claim generation.
- Evidence (measured): The first invocation was a launcher-path defect: the
  component was staged at the guest root while the unchanged runner requires
  `inputs/gemma4-layer0-down-proj-component.safetensors`. Its persisted state
  had `science_started=false`, zero rows, and no CUDA arm.
- Evidence (measured): The same-claim corrected invocation then failed before
  science because the immutable component manifest has `only_tensor` while
  the unchanged runner requires `tensor_key`. Its persisted state again had
  `science_started=false`, zero rows, and no terminal. Guest verification was
  0 MiB GPU memory, 0% utilization, and no runner process. The exact bound
  scientific bytes were not modified and no valid sample was consumed.
- Interpretation/next move: This is a typed binding/integration blocker, not
  a scientific negative. The binding forbids changing the manifest or runner,
  so the exact invocation cannot become valid in this turn. Both attempts and
  diagnostics are preserved under `artifacts/`; the exact claim was released
  generation-fenced to maintenance at 16:20:54Z. Director must rebind the
  manifest/runner contract before any future claim.

## 2026-07-29 — H200 gated-activation component is numerically negative

- Question/action: Consume the repaired compatibility manifest, preserving the
  component, runner, kernel, shapes, consumer, and 100-repetition contract,
  and run the fresh M=1/16/32 component ledger once.
- Evidence (measured): Binding `d4b76ab4...`, compatibility manifest
  `b179e255...`, all immutable input hashes, reservation, watchdog, and named
  zero-GPU H200 verified. The corrected run crossed `science_started`, loaded
  the exact component, completed all three rows, candidate-path invocation
  proof, and both CUDA-graph arms. No endpoint science ran.
- Evidence (measured): M=1 numerical pass; M=16 and M=32 numerical failures.
  M=32 candidate component median was `0.052640 ms` versus baseline
  `0.074160 ms` (timing-positive), but activation relative-L2 was
  `0.002343` and consumer relative-L2 `0.002766`, above the `0.001` gate.
  The runner emitted `invalid_incomplete` because it conflates numerical
  failure with ledger completeness; the persisted rows, identity, graph proof,
  and candidate invocations are complete and decision-bearing.
- Interpretation/next move: Classify this mechanism as the typed scientific
  negative `component_negative_numerical_equivalence`, not as a timing winner
  or harness failure. The exact claim was released available at 16:29:42Z;
  no endpoint promotion is authorized.

## 2026-07-29 — exact stock arithmetic association source revision

- Question/action: Under binding `2199c142...`, localize the first arithmetic
  boundary between the closed fused producer and pinned SGLang v0.5.13, then
  prepare one materially revised candidate without GPU work or sample replay.
- Evidence (source-backed): The stock JIT `GeluAndMul` casts to BF16 once after
  `apply_activation_f32(gate) * up`, so the closed candidate already preserved
  the required BF16 materialization before scale reduction. The first source
  mismatch is the GELU cubic: stock evaluates
  `((alpha * gate) * gate) * gate`; the closed candidate evaluated
  `alpha * ((gate * gate) * gate)`.
- Evidence (synthetic deterministic CPU/static): Seeded BF16 M=1/16/32
  discriminators found 1,315 / 20,252 / 41,526 differing weighted-cubic
  intermediates. The revised source is expression-identical to stock at that
  boundary and retains the BF16 shared-memory activation before the unchanged
  row reduction and E4M3 conversion. Python compilation, static identity
  checks, and the future runner's real `--describe` entrypoint passed. This
  local proxy did not reproduce a post-BF16 difference and is not target-H200
  correctness or performance evidence.
- Interpretation/next move: Publish the revised source as GPU-fenced
  source-ready evidence. A later director may authorize one fresh exact
  component run; keep M=1/16/32, 100 repetitions, the real down projection,
  strict runner numerical gates, and endpoint prohibition unchanged. The
  closed measured bytes remain a consumed numerical negative.

## 2026-07-29 — fresh exact-rounding H200 ledger (terminal negative)

- Action: Claimed the named H200 at 16:50:26Z under rebind `4d0517f0…` and
  staged the hash-bound source/runner/component. The first rootless container
  launch stopped before identity validation or CUDA (`getpwuid(1001)`); its
  preserved invocation state has zero rows and `science_started: false`.
  Repaired only that launcher boundary in the same claim and used one fresh
  output generation.
- Evidence (measured): The repaired invocation consumed one target sample and
  retrieved a complete M=1/16/32 ledger, candidate-path proof, identity, and
  dual CUDA-graph proof at terminal `3ff1f93e…`. All candidate paths and
  graph arms pass. M32 component median fell from 0.073520 ms to 0.052800 ms
  (28.18%), but strict numerical gates fail at M16 (consumer relative-L2
  0.0043755) and M32 (0.0027664); only M1 passes.
- Interpretation: This is a decision-bearing numerical negative despite the
  component timing. The candidate is closed with no endpoint promotion or
  replay. The claim generation was released quiescent at 16:55:16Z; recorded
  conservative cumulative exposure is $1.60 of the $2.00 reservation.
