# Research log

## 2026-07-16 — Director opening handoff

Use the retained trace as the first stop: query-rank reduction has no KV-capacity benefit, so it is relevant only if q-a/q-b occupy enough exact serving time for a 3% endpoint path. Test rank640/512 paired through q-RMSNorm and close before expensive reconstruction when the impossible trace ceiling is insufficient.

## 2026-07-16 — Q_RANK_CLOSE from source-bound trace ceiling

Question: can rank 640 or 512 plausibly clear the required 3.5% endpoint reduction before a paired-channel reconstruction?

Action/evidence: parsed the retained v25r1 profiler trace from archive SHA-256 `9ce5d882…b3eb2e9`. The source-bound sequence is q-a fused with KV-a (`[8192,2048]x[2048,1344]`, 218.914 us), its q-a-to-norm bridge (5.385 us), q-RMSNorm/split (13.184 us), then q-b (`[8192,768]x[768,5120]`, 305.347 us). Kernel interval unions—not summed overlapping launches—were used. Giving the candidate every favorable assumption (all 47 layers transfer, no overhead, linear removal of only the altered channels) yields only 0.0964% at rank 640 and 0.1927% at rank 512, or 602.738/603.320 tok/s from the 602.157 tok/s c32 anchor.

Interpretation: even the larger 512 reduction is 18.2x below the 3.5% impossible-endpoint gate and remains below the 606.355 tok/s economic threshold. The evidence closes this lineage before tensor payload reconstruction; the trace artifact is [`artifacts/Q_RANK_TRACE_CEILING_2026-07-16.json`](artifacts/Q_RANK_TRACE_CEILING_2026-07-16.json). No checkpoint/runtime/CUDA/provider mutation or successor preparation occurred.
