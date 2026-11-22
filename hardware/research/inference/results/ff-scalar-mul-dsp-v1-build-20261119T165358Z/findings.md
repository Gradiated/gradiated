# Experiment 19 · Routed exact feed-forward scalar multiplier

Vivado 2025.2 fully routed the candidate at 50 MHz. Worst setup slack was 4.060 ns and worst hold slack was 0.015 ns. The retained Experiment 18 control has 4.211 ns setup slack and 0.013 ns hold slack. The candidate passed clock coverage and design rule checks with zero routing gaps, zero active unclocked pins and zero unconstrained internal endpoints.

| Resource | Experiment 18 control | Candidate | Change |
| --- | ---: | ---: | ---: |
| CLB LUTs | 38,383 | 38,350 | -33 |
| Registers | 14,466 | 14,978 | +512 |
| DSP blocks | 41 | 53 | +12 |
| Block RAM tiles | 39 | 39 | +0 |
| LUTs used as memory | 1,172 | 1,172 | +0 |
| UltraRAM | 0 | 0 | +0 |
| Feed-forward hierarchy, LUTs | 5,466 | 5,419 | -47 |
| Feed-forward hierarchy, registers | 1,506 | 2,010 | +504 |
| Feed-forward hierarchy, DSP blocks | 7 | 19 | +12 |
| Feed-forward scalar, LUTs | 4,757 | 4,709 | -48 |
| Feed-forward scalar, registers | 988 | 1,492 | +504 |
| Feed-forward scalar, DSP blocks | 4 | 16 | +12 |

The build reused the exact Experiment 18 control checkpoint and all 119 pinned shell inputs. The generated PS and neural port maps and the AXI address map match. The only changed compiled neural source is `feedforward.sv`, where the candidate replaces the product implementation in `fixed_scalar_ff_exp`. Counts come from Vivado's routed hierarchical report. Some grouped LUTRAM and leaf entries in the raw census describe the same occupied resources.

The bounded remote flow took 969.7 seconds, including image conversion and the mapped primitive census. Recovery verified all 329 archived members. The binary firmware matches the converted Xilinx payload and the program overlay names that image. Human attention and AI usage costs are unknown.

[Run record](run.json) · [RTL qualification](../ff-scalar-mul-dsp-v1-rtl-20261119T165532Z/findings.md) · [Experiment 18 route](../probability-div-v1-build-20261119T155633Z/findings.md) · [Protocol](../../experiments/kv260-scalar-product-opportunity-v1.md)
