# Research log

## 2026-07-30 — deterministic mechanism falsification

Question: can the pinned SGLang v0.5.13 c32 scheduler legally merge two or
three adjacent Gemma 4 decode ticks into layer-consistent M64/M96 FP8
linears?

Action: hash-bound the pinned runtime source, the exact non-spec c32 FP8
consumer audit, the qualified NGRAM c32 consumer and token-event traces, the
model config, and the H200 inventory. Reconstructed the scheduler-to-sampling
dependency and both observed decode geometries with
`cross_tick_coalescing_falsifier.py`. The command was run twice; both runs
produced byte-identical trace and terminal artifacts.

Evidence:

- Source proves one KV position is allocated per active request, the complete
  60-layer target forward precedes sampling, and the sampled token becomes
  input only on the following scheduler iteration.
- The non-spec trace has 240 exact dense-linear consumer rows, all M32. The
  completed workload implies 357 steady decode ticks and 11,424 steady rows.
- The qualified c32 endpoint uses 12 NGRAM verification rows per request. Its
  240 exact consumers are all M384; reconstructed token events contain 32
  full c32 waves, each corresponding to 384 target-verification rows.
- QKV plus gate/up and down FP8 weights total 26.31401472 GB per non-spec
  tick. At the inventory's 4.8 TB/s H200 bandwidth, the single-stream weight
  floor is 5.4820864 ms/tick.
- Even an impossible zero-overhead M64/M96 ideal is bounded to 5.5913% or
  7.4550% of the recorded whole capture when scaled by measured nonoverlapping
  decode-FP8 attribution, below the fixed 20% campaign objective.

Interpretation: future rows from the same c32 requests do not exist until the
current full forward and sampling complete. A second independent cohort would
exceed the admitted c32 resident geometry or delay rows already present.
Furthermore, the qualified endpoint has already transformed its target
linear geometry to M384. A hold-and-concatenate source patch would therefore
change semantics or test a different mechanism.

Decision: `typed_physical_semantic_negative`. Close only consecutive-tick
M64/M96 scheduler coalescing and its transfer to the qualified NGRAM endpoint.
Do not close within-tick kernels, persistent weight-resident execution,
qualified M384 target-verification optimization, or a separately proven
lossless predictor. No GPU was claimed, CUDA was not invoked, provider state
was not mutated, and spend remained `$0.00`.

Artifacts:

- `TRACE_RECONSTRUCTION.json`:
  `a616600a25949e6995c86c49af3f1cf6ec14b065fd2d8355ff9258fc919c3aad`
- `MECHANISM_TERMINAL.json`:
  `e33b23644177d2d7238b5532ff9b581020768bd7f66ecd2265cdd8d86b4bdf28`
- `EXPERIMENT_SPEC.json`:
  `b053b75f1c74d555ddd9ee0064ed0ef959215df08842bd236ace44d2c26206b2`
- `cross_tick_coalescing_falsifier.py`:
  `9812059b9724cfbfc65a2eb0362d2e07447de5315e734550bd7bc32962ec3acc`

Next move: the director may redirect effort to one of the explicitly open
mechanisms. Reopen this lane only when a falsification condition in
`MECHANISM_TERMINAL.json` is satisfied with exact source and trace evidence.
