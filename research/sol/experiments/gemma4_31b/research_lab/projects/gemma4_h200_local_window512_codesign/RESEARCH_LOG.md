# Research log

## 2026-07-23 — director admission

Admitted one model/hardware co-design proxy after two exact local-attention kernel redesigns closed. The candidate changes only the 50 local layers' window from 1,024 to 512 and is explicitly barred from production promotion without separate quality validation or recovery. No GPU has been claimed.

## 2026-07-23 — offline path bound and typed H200 storage boundary

Question: can the exact 1,024→512 local-window proxy reach the endpoint gate, and is the retained H200 executable after the higher-priority n-gram lane?

Action: materialized the pinned model config, 62.58-GB checkpoint, current stacked-runtime inputs, Gemma4 source, and `_fwd_kernel` source under this project. `PATH_BINDING.json` binds `config.json`'s 50-local/10-global pattern through `Gemma4Attention.sliding_window`, `RadixAttention`, `TritonAttnBackend.forward_extend`, and `_fwd_kernel.SLIDING_WINDOW_SIZE`. Implemented the one-shot component/reference check, local-only source patch with 50/10 runtime audit, conditional exact c32 pair, and bounded pool owner. No GPU was claimed.

Evidence: `PHYSICAL_BOUND.json` counts the pinned kernel's non-skipped 64×64 QK/V tiles at the admitted boundary and observed grid-z2/grid-z32 shapes. Window 512 removes 42.857–47.059% of active tiles; the conservative value times the measured 15.312032% local-kernel wall fraction is a 6.562299% whole-request opportunity bound, or `0.630075 s/request` from the current `0.674326` control. This passes both the 5% and `0.6381105231 s/request` analytical gates but remains an analytical bound, not measured latency.

The higher-priority n-gram lane then produced new external evidence: its separate 62.58-GB remote immutable checkpoint staging failed with `ENOSPC` before CUDA and it released `h200-sync-linear-e00vhh6h29fj68x91g` to maintenance. `EXTERNAL_BLOCKER.json` records that the same snapshot rule applies here; bypassing it by mounting another project's remote checkpoint is forbidden. This project's candidate CUDA/scientific invocation did not start, its arm is unconsumed, and cumulative provider exposure remains `$0.00`.

Interpretation/next: the physical gate justifies measurement, but the sole admitted bench is not safely executable. Director disposition requires a compatible lab-owned H200 returned ready with at least 62.58 GB free for this project's immutable snapshot and at least 25 minutes of lifecycle after staging. Then run the already materialized component/path check and conditional sole c32 pair without changing geometry.
