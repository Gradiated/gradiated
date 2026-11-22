# Experiment 18 · Routed exact attention probability divider

Vivado 2025.2 fully routed the candidate at 50 MHz. Worst setup slack was 4.211 ns and worst hold slack was 0.013 ns. The retained Experiment 13 control has 5.544 ns setup slack and 0.012 ns hold slack. The candidate passed clock coverage and design rule checks with zero routing gaps, zero active unclocked pins and zero unconstrained internal endpoints.

| Resource | Experiment 13 control | Candidate | Change |
| --- | ---: | ---: | ---: |
| CLB LUTs | 38,329 | 38,383 | +54 |
| Registers | 14,464 | 14,466 | +2 |
| DSP blocks | 41 | 41 | +0 |
| Block RAM tiles | 39 | 39 | +0 |
| LUTs used as memory | 1,172 | 1,172 | +0 |
| UltraRAM | 0 | 0 | +0 |
| Attention hierarchy, LUTs | 9,397 | 9,444 | +47 |
| Attention hierarchy, registers | 2,220 | 2,223 | +3 |
| Primary attention scalar, LUTs | 4,911 | 5,032 | +121 |
| Primary attention scalar, registers | 982 | 983 | +1 |
| Second exponential, LUTs | 3,788 | 3,709 | -79 |
| Second exponential, registers | 855 | 854 | -1 |

The build reused the exact Experiment 13 control checkpoint and all 119 pinned external shell inputs. The generated PS and neural port maps and AXI address map match. The only changed compiled neural source is `attention.sv`. The memory and DSP census found 0 changed named rows outside attention. The hierarchy counts come from Vivado's routed report. Some grouped LUTRAM and leaf entries in the raw census describe the same occupied resources.

The bounded remote flow took 912.2 seconds, including image conversion and the candidate primitive census. Recovery verified all 323 archived members. The binary firmware matches the converted Xilinx payload and the overlay names that image. This record reports implementation timing and resources. Latency and energy use the board protocol. Human attention and AI usage costs are unknown.

[Run record](run.json) · [RTL qualification](../probability-div-v1-rtl-20261119T160135Z/findings.md) · [Experiment 13 route](../attention-exp-pair-v2-build-20261117T225852Z/findings.md) · [Protocol](../../experiments/kv260-probability-div-v1.md)
