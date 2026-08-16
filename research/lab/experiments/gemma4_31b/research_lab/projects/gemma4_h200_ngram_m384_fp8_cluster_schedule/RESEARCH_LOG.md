# Research log

## 2026-07-24 — director delegation

Measured evidence binds a new exact-shape kernel question. The repaired c32
NGRAM trace reports `1.163217634 s` of summed FP8 CUTLASS kernel time in a
`3.165732460 s` trace window and names the stock
`128x128x128`, `2x1x1`, SM90 ping-pong fast-accumulation kernel. Fixed
target verification produces `32 x 12 = 384` rows, or three 128-row M tiles,
which leaves a partial two-CTA M cluster.

The completed wave terminal rules out draft-depth reduction as the immediate
replacement: its final accepted length was `11.828571` with `98.4416%`
acceptance. The QLEN component remains exact and positive evidence, but three
endpoint/observer integrations have not proven its production path; do not
replay that line in this project.

Run exactly one M384-only `1x2x1` cluster orientation with `$kernel-research`.
All other GEMMs and serving behavior remain stock. The first paid evidence is
the exact real-weight component, followed conditionally by one candidate-only
c32 endpoint against the persisted valid stock control.

## 2026-07-24 — exact M384 component closes 1x2x1

- **Question/action:** Hash-verified the director binding and every cited input,
  froze one `M == 384` CUTLASS candidate that changed only the cluster from
  `2x1x1` to `1x2x1`, and claimed the retained H200. The first comparator
  mistakenly entered during CUDA-graph capture; that invalid attempt was
  preserved. The repaired component ran eager only so the live NGRAM
  target-verification calls reached the unchanged real-weight
  `Fp8LinearMethod.apply -> fp8_utils.fp8_scaled_mm` consumer. Endpoint mode
  remained CUDA-graph enabled and conditional.
- **Measured evidence:** Exact live M384 was observed for all six affected
  shapes: local/global QKV, local/global `o_proj`, packed gate/up, and down.
  The modeled CTA count fell 25% for every shape, but every candidate output
  was non-bitwise and badly divergent; gate/up produced 584,726 nonfinite
  values and the runtime emitted SM90 architecture-conditional MMA guards.
  Across 20 warm repetitions per shape, stock medians summed to
  `777.328 us` versus `588,962.448 us` candidate time, a `757.68x` aggregate
  slowdown. The candidate compiled to 24 registers with zero spills, so
  register pressure does not explain the failure.
- **Decision:** Close only this exact M384 `1x2x1` orientation as unsupported /
  incorrect in the pinned production CUTLASS instantiation. The positive
  component gate failed; no candidate endpoint ran and the persisted
  `0.6049806232813353 s/request` control was not replayed. The bench was
  released available at `17:38:08Z`. Conservative total assigned exposure was
  `$0.6197179235`.
- **Artifacts:** `LATEST_TERMINAL.json`, `COMPONENT_MEASUREMENTS.jsonl`,
  `CANDIDATE_BUILD.json`, `CANDIDATE_BUILD.stdout`, and raw retained artifacts
  under `artifacts/m384-cluster-20260724t172301z/`.
