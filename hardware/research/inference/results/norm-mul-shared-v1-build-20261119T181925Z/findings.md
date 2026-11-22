# Experiment 21 · Routed exact RMSNorm multiplier

Vivado 2025.2 fully routed the candidate at 50 MHz. Worst setup slack was 5.418 ns and worst hold slack was 0.017 ns. The retained Experiment 20 control has 4.069 ns setup slack and 0.011 ns hold slack. The candidate passed clock coverage and design rule checks with zero routing gaps, zero active unclocked pins and zero unconstrained internal endpoints.

| Resource | Experiment 20 control | Candidate | Change |
| --- | ---: | ---: | ---: |
| CLB LUTs | 39,132 | 38,130 | -1,002 |
| Registers | 16,492 | 15,605 | -887 |
| DSP blocks | 89 | 57 | -32 |
| Block RAM tiles | 39 | 39 | +0 |
| LUTs used as memory | 1,174 | 1,172 | -2 |
| UltraRAM | 0 | 0 | +0 |
| Feed-forward hierarchy, LUTs | 5,442 | 5,398 | -44 |
| Feed-forward hierarchy, registers | 2,010 | 2,010 | +0 |
| Feed-forward hierarchy, DSP blocks | 19 | 19 | +0 |
| Feed-forward scalar, LUTs | 4,712 | 4,707 | -5 |
| Feed-forward scalar, registers | 1,492 | 1,492 | +0 |
| Feed-forward scalar, DSP blocks | 16 | 16 | +0 |
| First RMSNorm, LUTs | 6,537 | 5,964 | -573 |
| First RMSNorm, registers | 2,185 | 1,674 | -511 |
| First RMSNorm, DSP blocks | 16 | 0 | -16 |
| Second RMSNorm, LUTs | 6,525 | 5,939 | -586 |
| Second RMSNorm, registers | 2,185 | 1,675 | -510 |
| Second RMSNorm, DSP blocks | 16 | 0 | -16 |
| Final RMSNorm, LUTs | 6,537 | 5,907 | -630 |
| Final RMSNorm, registers | 2,185 | 1,676 | -509 |
| Final RMSNorm, DSP blocks | 16 | 0 | -16 |
| Shared RMSNorm multiplier, DSP blocks | 0 | 16 | +16 |

The build reused the exact Experiment 20 control checkpoint and all 119 pinned shell inputs. The generated PS and neural port maps and the AXI address map match. Only `rmsnorm.sv`, `transformer.sv` had different supplied RTL bytes. The selected sites were `norm1.scalar`, `norm2.scalar`, `normfinal.scalar`, `norm_mul`. Vivado kept all 11 supplied source pins and used 10 files in the active hierarchy. The generic `fixed_scalar.sv` module was supplied unchanged and has no active instantiations. Counts come from Vivado's routed hierarchical report. Some grouped LUTRAM and leaf entries in the raw census describe the same occupied resources.

The bounded remote flow took 1014.0 seconds, including image conversion and the mapped primitive census. Recovery verified all 328 archived members. The binary firmware matches the converted Xilinx payload and the program overlay names that image. Human attention and AI usage costs are unknown.

[Run record](run.json) · [RTL qualification](../norm-mul-shared-v1-rtl-20261119T175457Z/findings.md) · [Experiment 20 route](../norm-mul-dsp-v1-build-20261119T175758Z/findings.md) · [Protocol](../../experiments/kv260-norm-mul-shared-v1.md)
