# Research log

## 2026-07-17 — director admission

Activated as independent `$0` evidence while the sole H200 owner prepares exact-shape BF16 measurement. Read-only exact-checkpoint analysis only; no provider, CUDA, copied checkpoint, or dependence on the live owner's terminal.

## 2026-07-17 — terminal exact-checkpoint screen

- **Question:** Do natural 2:4 structure, deterministic magnitude 2:4, or bounded low-rank energy justify one later quality-aware H200 model-change experiment?
- **Action:** Inventoried all 410 exact in-scope projection tensors with shard hashes and byte ranges; measured 18 stratified class-layer aggregates (30 tensors) using mmap BF16 chunks. Used exact 2:4 statistics and deterministic 384-column full-output Gram sketches at ranks 128/256.
- **Evidence:** `WEIGHT_STRUCTURE_SCREEN.json` (sha256 `ea7257c933b841733d31452f72c1843669bb59213b5e1cd6ccf8060377695216`) and `DECISION.md`. Natural zero/2:4 compliance was 0 throughout; magnitude 2:4 retained 86.29–89.09% energy; rank-256 minimum sketch energy was 73.59%. Runtime was 79.14 wall seconds and 289.58 CPU seconds; spend/CUDA/provider mutation were zero.
- **Interpretation:** Large analytical byte ceilings do not rescue either mechanism: 2:4 fails natural structure and proxy-energy gates, and low rank fails the cross-layer sketch-energy gate. Global layers also lack a standalone `v_proj`; no synthetic missing tensor was imputed.
- **Next move:** Typed future candidate `none`; close this line. Do not spend H200 or quality-evaluation budget on these interventions from this evidence.
