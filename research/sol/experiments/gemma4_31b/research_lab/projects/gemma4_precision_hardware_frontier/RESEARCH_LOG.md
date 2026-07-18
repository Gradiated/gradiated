# Research log

## 2026-07-18 — exact H200 FP8 falsifier prepared; pool claim blocked

Question: can one authenticated checkpoint-free exact-shape measurement show at least 20% component-cost margin for a supported precision/hardware pair over H200 BF16?

Action: ranked the shared price/capability inventory, selected H200 native E4M3 versus BF16, and implemented `h200_fp8_exact_shape_falsifier.py`. It invokes the real `torch._scaled_mm` symbol on all six Gemma text-linear shapes at M12 decode and M3679 prefill, the tied 262144x5376 head, BF16 local/global decode attention, and BF16/E5M2 local/global KV writes. Timed outputs feed numerical oracles and the weighted component-floor aggregation. Three atomic pool claims were attempted; all failed because `gemma4_h200_critical_path_profile` had claimed the only compatible bench first.

Evidence: `artifacts/20260718t1532z-blocked/FRONTIER.json` records committed-price break-even thresholds (L40S 0.338x, MI355X 0.800x, H100 SXM 0.862x, B200 1.585x H200 throughput) and no endpoint nominee. `artifacts/20260718t1532z-blocked/TERMINAL.json` records the typed pool blocker, zero spend, exact bench identity/deadline, and the minimum reusable bench contract. The runner compiles locally, but no scientific acceptance boolean is inferred from that.

Interpretation: H200 FP8 remains the only authenticated shortest falsifier, but no measured frontier exists. The concurrent claim and imminent watchdog deadline are external execution availability, not a precision result. RTX 6000 Ada, MI300X/MI325X, and MI210 cannot be canonically price-ranked because the shared price inventory has no committed planning rate; L40S and H100 prior component evidence does not establish endpoint admission.

Next move: on the first compatible bench with at least ten safe lifecycle minutes, run the prepared runner once, retrieve `SENTINEL.json` and the terminal result, compute the measured frontier, and nominate H200 FP8 only if every oracle passes and weighted component margin is at least 20%.
