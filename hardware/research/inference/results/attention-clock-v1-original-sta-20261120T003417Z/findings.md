# Experiment 24 · Static timing on the adopted layout

The exact Experiment 23 programming image qualifies at 50 MHz and the predicted ≈52.63 MHz divider rate. Vivado reported a setup failure at the 62.5 MHz stretch target on that layout.

| Configured-rate arm | Analysed period (ns) | Setup slack (ns) | Hold slack (ns) | Pulse-width slack (ns) | Setup failing endpoints |
| --- | ---: | ---: | ---: | ---: | ---: |
| 50 MHz | 20.000 | +1.390 | +0.005 | +8.500 | 0 |
| 52.63 MHz | 18.999 | +0.389 | +0.005 | +7.999 | 0 |
| 62.5 MHz | 15.999 | -2.611 | +0.005 | +6.499 | 64 |

Each analysis covered 55,096 setup endpoints, 55,096 hold endpoints and 17,199 pulse-width endpoints. All designed fabric clock sinks trace to the sole PS8 PL0 domain. Native reports show zero unclocked or unconstrained internal endpoints and zero route gaps, routing errors or DRC errors/critical warnings. Runtime constraints differ only by the clock period. The adopted checkpoint and image hashes match their saved copies.

Vivado reports 18.366 ns of data path delay on the limiting attention scalar path, including 6.215 ns of logic and 12.151 ns of routing. At the stretch target total negative setup slack was −157.231 ns. The first timing runner stopped during audit initialization and its raw log is retained.

[Run record](run.json) · [Experiment 23 route](../attention-value-pair-v1-build-20261119T203714Z/findings.md) · [Protocol](../../experiments/kv260-clock-frequency-v1.md)
