# Observation-counter offline build

The separately named counter circuit passed routing, final reports and offline bitstream generation. It has not been programmed onto the KV260. The original circuit and frozen model remain unchanged.

| Routed full-design resource | Original | Observer | Change |
| --- | ---: | ---: | ---: |
| LUTs | 31,792 | 32,553 | +761 |
| Registers | 11,027 | 12,044 | +1,017 |
| DSPs | 10 | 10 | 0 |
| Block-RAM tiles | 36.5 | 36.5 | 0 |
| Occupied CLBs | 5,386 | 5,764 | +378 |

LUT utilisation rises from 27.14% to 27.79%, register utilisation from 4.71% to 5.14%, and occupied CLBs from 36.79% to 39.37%. These are resource categories, not physical chip area. Placement and optimisation can contribute to the differences.

At the unchanged 20 ns clock target, setup slack is +4.725 ns and hold slack +0.013 ns. The original reports were +4.913 ns and +0.011 ns respectively. Routing is complete, with no clock gaps, unclocked active pins, unconstrained internal endpoints, black boxes, latches, DRC errors or critical warnings. The same 32 DSP-pipelining advisory warnings remain. No constraints or severities were waived.

Routing resumed from the verified placed checkpoint and took 500.30 s, reports 72.07 s and bitstream generation 113.98 s, within the 600/180/180 s limits. The earlier user-interrupted route and all 258 pre-restart files are preserved unchanged. The complete server archive was copied and checked on the Mac, along with individual file hashes. Bootgen conversion was independently checked against the exact word-swapped configuration payload. SOL independently verified unchanged generated clock/reset wiring.

The prerequisite RTL simulation covered two BOS requests and 640 exact scores, cycle-identical legacy AXI traces, reset/read races and overflow. Those checks are simulation evidence. This build adds no physical speed, energy or counter evidence.

Next: review the exact physical packet, obtain explicit approval for temporary observer programming, then compare it against the original image with the original software wrapper. Restore the original image and weights on healthy completion and verify them. Keep counter reads outside the complete power window. Stop before selecting the broader roadmap step 4 experiments.

[Run record](run.json) · [Protocol](../../experiments/kv260-observer-v1.md) · [Source](../../implementations/kv260/variants/observer-v1/README.md)
