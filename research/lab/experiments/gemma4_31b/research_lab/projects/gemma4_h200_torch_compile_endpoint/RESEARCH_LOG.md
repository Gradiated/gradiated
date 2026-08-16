## 2026-07-18 — Torch-compiled fused c32 endpoint

Measured: the pinned compiled path completed its initial bs32 graph capture and served one exact 32-row mix. The compiled path was enabled and consumed; all outputs were valid and cache accounting was exactly 17,120 cached / 117,728 fresh. Service time was 0.936788648094 s/request, 1.885% slower than the frozen 0.919457394125 comparator. Classified `negative`; no tuning or comparator rerun. Artifacts: `artifacts/torch-compile-fused-c32-20260718t1827z/`.
