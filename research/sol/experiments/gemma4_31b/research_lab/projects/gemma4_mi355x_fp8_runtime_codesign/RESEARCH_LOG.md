# Research log

## 2026-07-26T07:36Z — admitted

Admitted as a zero-provider-spend deep mechanism lane while the independent
H100 registered-Attention component remains claimed. The first terminal must
be executable exact-geometry evidence or a typed negative, not a survey.

## 2026-07-26T07:57Z — source-complete candidate

Question: does the exact BF16 production checkpoint reach current gfx950 FP8
linear and hybrid-attention consumers, and can a conservative physical-cost
screen clear the `$2.60/hour` hurdle without NVIDIA timing transfer?

Action: pinned vLLM `0164022c907014a27e81c514cd4dff6091904c2b` and AITER
`6c48c5fa0e7c299adcf1987c8f4817720ceab311`, hashed every decision-bearing
source file, and executed `run_mi355x_runtime_screen.py` against those bytes.
The discriminator extracted all exact local/global linear, FP8-KV, attention,
normalization, and BF16 tied-head shapes for prefill, M32 decode, and M384
target verification.

Evidence:

- Source-backed/executed: online BF16 transformer weights become per-tensor
  E4M3FN and reach ROCm `torch._scaled_mm`; AITER per-token FP8 linears reject
  that scale contract. Hybrid attention reaches AITER flash/unified attention,
  while the tied embedding/head remains BF16.
- Analytical/inferred: a zero-L2, 20%-matrix, 30%-HBM, 3-us-launch, 40-ms
  service-reserve envelope is `0.6000950932112802 s/request`, versus the
  `0.625149101968745` base hurdle. It clears by `0.025054008757464774 s`.
- Derived: the 2x runtime-fragmentation memory envelope is 91,396,365,744
  bytes on a 288-GB TP1 device. No interconnect is credited.
- Negative sensitivity: the same envelope does not clear the `$2.75/hour`
  (`0.5910500600431771 s`) or `$2.95/hour` (`0.5509788695317752 s`) hurdles.

Interpretation: emit `MI355X_FP8_RUNTIME_SCREEN.json` as
`source_complete_mi355x_candidate`. This preserves exactly one later
20-minute MI355X exact-shape falsifier; it does not claim measured throughput,
quality, endpoint behavior, or deployability.

Boundary: no GPU was claimed, no provider was contacted or mutated, the H100
owner was not waited on, and cumulative provider spend remains `$0.00`.
