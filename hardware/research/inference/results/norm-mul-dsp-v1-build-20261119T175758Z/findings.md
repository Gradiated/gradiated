# Experiment 20 · Routed exact RMSNorm multiplier

Vivado 2025.2 fully routed the candidate at 50 MHz. Worst setup slack was 4.069 ns and worst hold slack was 0.011 ns. The retained Experiment 19 control has 4.060 ns setup slack and 0.015 ns hold slack. The candidate passed clock coverage and design rule checks with zero routing gaps, zero active unclocked pins and zero unconstrained internal endpoints.

| Resource | Experiment 19 control | Candidate | Change |
| --- | ---: | ---: | ---: |
| CLB LUTs | 38,350 | 39,132 | +782 |
| Registers | 14,978 | 16,492 | +1,514 |
| DSP blocks | 53 | 89 | +36 |
| Block RAM tiles | 39 | 39 | +0 |
| LUTs used as memory | 1,172 | 1,174 | +2 |
| UltraRAM | 0 | 0 | +0 |
| Feed-forward hierarchy, LUTs | 5,419 | 5,442 | +23 |
| Feed-forward hierarchy, registers | 2,010 | 2,010 | +0 |
| Feed-forward hierarchy, DSP blocks | 19 | 19 | +0 |
| Feed-forward scalar, LUTs | 4,709 | 4,712 | +3 |
| Feed-forward scalar, registers | 1,492 | 1,492 | +0 |
| Feed-forward scalar, DSP blocks | 16 | 16 | +0 |
| First RMSNorm, LUTs | 6,356 | 6,537 | +181 |
| First RMSNorm, registers | 1,689 | 2,185 | +496 |
| First RMSNorm, DSP blocks | 4 | 16 | +12 |
| Second RMSNorm, LUTs | 6,314 | 6,525 | +211 |
| Second RMSNorm, registers | 1,687 | 2,185 | +498 |
| Second RMSNorm, DSP blocks | 4 | 16 | +12 |
| Final RMSNorm, LUTs | 6,246 | 6,537 | +291 |
| Final RMSNorm, registers | 1,688 | 2,185 | +497 |
| Final RMSNorm, DSP blocks | 4 | 16 | +12 |

The build reused the exact Experiment 19 control checkpoint and all 119 pinned shell inputs. The generated PS and neural port maps and the AXI address map match. Only `rmsnorm.sv` had different supplied RTL bytes. The selected sites were `norm1.scalar`, `norm2.scalar`, `normfinal.scalar`. Vivado kept all 11 supplied source pins and used 10 files in the active hierarchy. The generic `fixed_scalar.sv` module was supplied unchanged and has no active instantiations. Counts come from Vivado's routed hierarchical report. Some grouped LUTRAM and leaf entries in the raw census describe the same occupied resources.

The bounded remote flow took 1097.9 seconds, including image conversion and the mapped primitive census. Recovery verified all 328 archived members. The binary firmware matches the converted Xilinx payload and the program overlay names that image. Human attention and AI usage costs are unknown.

[Run record](run.json) · [RTL qualification](../norm-mul-dsp-v1-rtl-20261119T175201Z/findings.md) · [Experiment 19 route](../ff-scalar-mul-dsp-v1-build-20261119T165358Z/findings.md) · [Protocol](../../experiments/kv260-norm-mul-dsp-v1.md) · [Earlier generation attempt](../norm-mul-dsp-v1-build-20261119T175345Z/findings.md)
