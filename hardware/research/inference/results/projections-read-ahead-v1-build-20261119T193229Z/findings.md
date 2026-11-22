# Experiment 22 · Routed within-row projection read-ahead

Vivado 2025.2 fully routed the candidate at 50 MHz. Worst setup slack was 4.027 ns and worst hold slack was 0.012 ns. The retained Experiment 21 control has 5.418 ns setup slack and 0.017 ns hold slack. The candidate passed clock coverage and design rule checks with zero routing gaps, zero active unclocked pins and zero unconstrained internal endpoints.

| Resource | Experiment 21 control | Candidate | Change |
| --- | ---: | ---: | ---: |
| CLB LUTs | 38,130 | 38,178 | +48 |
| Registers | 15,605 | 15,595 | -10 |
| DSP blocks | 57 | 57 | +0 |
| Block RAM tiles | 39 | 39 | +0 |
| LUTs used as memory | 1,172 | 1,172 | +0 |
| UltraRAM | 0 | 0 | +0 |
| QKV projection, LUTs | 135 | 150 | +15 |
| QKV projection, registers | 82 | 80 | -2 |
| QKV projection, DSP blocks | 1 | 1 | +0 |
| QKV projection, BRAM tiles | 2 | 2 | +0 |
| Attention output projection, LUTs | 252 | 265 | +13 |
| Attention output projection, registers | 78 | 78 | +0 |
| Attention output projection, DSP blocks | 1 | 1 | +0 |
| Attention output projection, BRAM tiles | 0.5 | 0.5 | +0 |
| Feed-forward gate projection, LUTs | 167 | 194 | +27 |
| Feed-forward gate projection, registers | 80 | 80 | +0 |
| Feed-forward gate projection, DSP blocks | 1 | 1 | +0 |
| Feed-forward gate projection, BRAM tiles | 2 | 2 | +0 |
| Feed-forward up projection, LUTs | 181 | 185 | +4 |
| Feed-forward up projection, registers | 80 | 80 | +0 |
| Feed-forward up projection, DSP blocks | 1 | 1 | +0 |
| Feed-forward up projection, BRAM tiles | 2 | 2 | +0 |

The build reused the exact Experiment 21 control checkpoint and all 119 pinned shell inputs. The generated PS and neural port maps and the AXI address map match. Only `feedforward.sv`, `frontend.sv`, `transformer.sv` had different supplied RTL bytes. The selected sites were `frontend.projection`, `transformer.output_projection`, `feedforward.gate_dense`, `feedforward.up_dense`. Both arms supplied the same 11 RTL filenames. The control used 10 files in the active hierarchy and the candidate used 8. The candidate supplied `fixed_scalar.sv`, `mac32.sv`, `dense.sv` unchanged, with no active instances of their modules. Counts come from Vivado's routed hierarchical report. Some grouped LUTRAM and leaf entries in the raw census describe the same occupied resources.

The bounded remote flow took 1129.6 seconds, including image conversion and the mapped primitive census. Recovery verified all 338 archived members. The binary firmware matches the converted Xilinx payload and the program overlay names that image. Human attention and AI usage costs are unknown.

[Run record](run.json) · [RTL qualification](../projections-read-ahead-v1-rtl-20261119T192912Z/findings.md) · [Experiment 21 route](../norm-mul-shared-v1-build-20261119T181925Z/findings.md) · [Protocol](../../experiments/kv260-projections-read-ahead-v1.md)
