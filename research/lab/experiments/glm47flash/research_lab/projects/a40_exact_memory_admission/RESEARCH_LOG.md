# Research log

## 2026-07-15 — exact MLA memory admission

Question: does the current `ab31d120` AWQ checkpoint admit an A40 48 GiB c8/c16 load, and is the TensorDock target physically falsified offline?

Action: parsed all 28,221 exact safetensor headers and the config/index, then reproduced vLLM 0.15.0's MLA cache geometry and its profile-based KV allocation accounting in `a40_admission.py`. The pinned source tarball SHA-256 and all formulas/inputs are bound in `A40_ADMISSION_RESULT.json`; no provider, GPU, model load, or credential was used.

Evidence: MLA stores one BF16 576-wide vector per layer, giving 54,144 B/token and 3.718/7.436/14.871 GiB live KV at c8/c16/c32. Against the 43.2 GiB 90%-utilization ceiling, the deliberately conservative 10 GiB non-KV band leaves 10.551 GiB at c8 and 6.833 GiB at c16; c32 is -0.603 GiB in that band but remains below the hard and source-derived expected bands. Historical L40S profile logs independently report 17.87 GiB model, 16.82 GiB KV, and imply 5.799 GiB non-KV; they are calibration only.

Interpretation: c8 and c16 are safely admissible by capacity. c32 requires the one exact-load measurement. At the all-in 10% lifecycle rate, the 5%/$0.60 gates require 166.819/176.968 output tok/s. The c8 ideal-reuse physical bandwidth floor at the stronger gate is 114.959 GB/s (16.5% of 696 GB/s); an expert-diverse stress case is 269.495 GB/s (38.7%), so no physical/economic lower bound kills A40. The corresponding arithmetic floor is 1.377 TFLOP/s (0.92% of the vendor 149.7 BF16-Tensor-TFLOP/s peak). This is not a throughput prediction.

Next move: retain exactly one later A40 exact-load c8/c16 measurement only after authenticated TensorDock account/funding plus delete/direct-instance authority; do not seek c32 first.
