# Experiment 24 · Timing-targeted stretch route

The separate timing-driven layout did not qualify a 62.5 MHz programming image. The original layout remains qualified for 50 MHz and about 52.63 MHz.

| Clock arm | Setup slack (ns) | Hold slack (ns) | Pulse-width slack (ns) | Setup failing endpoints |
| --- | ---: | ---: | ---: | ---: |
| 50 MHz | +2.999 | +0.011 | +8.500 | 0 |
| 52.63 MHz | +1.998 | +0.011 | +7.999 | 0 |
| 62.5 MHz | -1.002 | +0.011 | +6.499 | 64 |

The routed stretch layout uses 39,425 LUTs, 15,753 registers, 58 DSPs and 39 BRAM tiles.

The new layout starts from the exact Experiment 23 synthesis checkpoint. Vivado ran Explore optimisation, placement, physical optimisation and routing with a 15.999 ns PL0 clock constraint. The existing PS and AXI interface and exact model arithmetic remained in scope throughout. The archive retains native hold, pulse-width, clock, endpoint and DRC evidence.

[Run record](run.json) · [Original layout](../attention-clock-v1-original-sta-20261120T003417Z/findings.md) · [Protocol](../../experiments/kv260-clock-frequency-v1.md)
