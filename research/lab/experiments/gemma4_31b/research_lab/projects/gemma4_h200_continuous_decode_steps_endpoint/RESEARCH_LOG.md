# Research log

## 2026-07-18 — delegated one exact continuous-decode candidate

Question: can four source-supported continuous decode steps reduce canonical c32 service time by amortizing scheduler overhead, accepting the documented TTFT trade for the campaign's background-agent workload?

Contract: reuse the released H200, resident exact checkpoint, and pinned SGLang image. Change only continuous decode steps from 1 to 4 on the retained dynamic-chunking/fused-QK/Triton baseline, invoke the frozen exact-mix consumer once after an idle HTTP-200 flush boundary, require exact output/cache accounting, retrieve a typed terminal, and release without teardown. No tuning, repair, comparator replay, setup replay, allocation, or lifecycle mutation is authorized.

## 2026-07-18 — exact step-4 candidate is negative

Question: can four continuous decode steps amortize scheduling enough to improve the retained exact c32 endpoint?

Action and evidence: claimed `h200-attention-endpoint-e00vbbb709tzxscaan`, removed only the failed TRTLLM container, and ran one durable owner, `gemma4-continuous-decode-steps-c32-20260718t1954z.service`. The live server log proves BF16 weights, FP8-E5M2 KV, dynamic chunking 2048, fused QK/RoPE, Triton prefill/decode, page size 1, and `num_continuous_decode_steps=4`; idle metrics and the HTTP-200 flush passed. The frozen runner (`143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`) ran exactly once. It produced 32/32 valid 4,214/358 rows, with exactly 17,120 cached and 117,728 fresh prompt tokens. Retrieved terminal: `artifacts/continuous-decode-steps-c32-20260718t1954z/TERMINAL.json` (`42d1da4cb01d31049ea4d8310786a7d8e77cf121e7763581ce0a27df7fe4ad37`).

Interpretation: service time was `0.930956860406` s/request, versus the frozen `0.919457394125` s/request control: a `-1.25068%` change, so it neither promotes nor qualifies as an incremental win. Mean TTFT was 9.436 s. This is the sole candidate and is terminal negative. The bench was released ready without teardown; its healthy step-4 server remains resident. Claimed exposure was 228.02643 seconds, conservatively accounted as `$0.1559` at `$2.46/hour`.
