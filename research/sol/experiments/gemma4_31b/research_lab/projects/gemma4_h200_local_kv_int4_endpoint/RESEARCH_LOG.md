# Research log

## 2026-07-23 — director admission

- Measured: attention/KV is `29.2729%` of exact-stack wall time and the 50 local layers account for `15.3120%`.
- Measured: stock FA3 cannot consume E5M2, while E4M3 KV slowed the endpoint; those exact representations remain closed.
- Derived: group-64 signed INT4 with FP16 scales reduces local stored/read bytes `46.875%`, yielding a theoretical whole-request ceiling near `7.18%` before unpack/dequant overhead.
- Hypothesis: direct packed production plus in-register Triton dequantization reduces local K/V DRAM sectors at least `35%` and preserves a conservative endpoint bound of at least `3%`.
- Decision: admit one fixed format and one actual-consumer component, with at most one conditional c32 pair. The result is quality-unqualified even if faster.

## 2026-07-23 — exact H200 producer/consumer rejects fixed INT4

- Question: can the admitted group-64 signed-INT4 local KV format preserve coherent attention while converting its 46.875% storage reduction into at least 35% lower local DRAM sectors and a 3% whole-request bound?
- Action: on the retained H200, executed one direct BF16-to-packed Triton producer and one page-one GQA online-softmax consumer adapted from pinned SGLang `decode_attention_fwd`, followed by the unchanged pinned reduction stage. The exact case covered c32/context-1024, shuffled page-one locations, negative padding no-op, padded graph batch 40, and a two-step append. One pre-producer Triton constexpr compile defect was repaired under the retained claim without consuming the arm. The completed producer/consumer was not replayed when the compact Nsight CSV parser needed an offline wide-format repair.
- Measured evidence: candidate output was finite but relative L2 was `0.1075067` (limit `0.05`) and cosine was `0.9942697` (minimum `0.995`). E5M2 control relative L2 versus the same BF16 paged oracle was `0.0536643`. The candidate stage used 255 registers/thread, two spills, and 25,600 bytes shared memory; control/candidate warm medians were `0.276512 ms` and `2.330816 ms`, an `8.43x` slowdown. Nsight measured `8,455,904` versus `4,490,280` DRAM read sectors, a passing `46.8977%` reduction; L2 read sectors fell from `12,834,772` to `7,919,374`.
- Interpretation: the byte hypothesis is physically real, but unpack/dequant live state drives the grouped stage to the Hopper register ceiling and erases the traffic win, while fixed group-64 INT4 also misses both numerical gates. The conservative whole-request timing bound is negative (`-113.76%` under the preregistered attribution formula), so endpoint promotion is forbidden.
- Decision: `component_reject`; do not run the conditional c32 pair and do not sweep group size, representation, or global E5M2. Canonical terminal: `artifacts/local-int4-component-20260723t1337z/repair1/retrieved/COMPONENT_TERMINAL.json` (`sha256 95810c1f3cf278ce3902265f5659cc5c4ea1967649d3b065958289ab385b864c`). The claim ran `899.77547 s` at `$2.46/h`; conservative project exposure is `$0.615`.
