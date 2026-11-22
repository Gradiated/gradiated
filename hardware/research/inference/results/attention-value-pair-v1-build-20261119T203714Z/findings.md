# Experiment 23 · Routed two-lane attention value mixing

Vivado 2025.2 fully routed the candidate at 50 MHz. Worst setup slack was 1.390 ns and worst hold slack was 0.005 ns. The retained Experiment 22 control has 4.027 ns setup slack and 0.012 ns hold slack. The candidate passed clock coverage and design rule checks with zero routing gaps, zero active unclocked pins and zero unconstrained internal endpoints.

| Resource | Experiment 22 control | Candidate | Change |
| --- | ---: | ---: | ---: |
| CLB LUTs | 38,178 | 39,376 | +1,198 |
| Registers | 15,595 | 15,712 | +117 |
| DSP blocks | 57 | 58 | +1 |
| Block RAM tiles | 39 | 39 | +0 |
| LUTs used as memory | 1,172 | 1,172 | +0 |
| UltraRAM | 0 | 0 | +0 |
| Attention hierarchy, LUTs | 9,442 | 10,613 | +1,171 |
| Attention hierarchy, registers | 2,220 | 2,335 | +115 |
| Attention hierarchy, DSP blocks | 9 | 10 | +1 |
| Attention hierarchy, BRAM tiles | 2 | 2 | +0 |
| KV cache, LUTs | 299 | 324 | +25 |
| KV cache, registers | 28 | 29 | +1 |
| KV cache, DSP blocks | 0 | 0 | +0 |
| KV cache, BRAM tiles | 8 | 8 | +0 |
| Frontend hierarchy, LUTs | 1,502 | 1,530 | +28 |
| Frontend hierarchy, registers | 1,337 | 1,335 | -2 |
| Frontend hierarchy, DSP blocks | 4 | 4 | +0 |
| Frontend hierarchy, BRAM tiles | 12 | 12 | +0 |

| Arm and bank | Logical depth × width | Routed memory types | Connected BRAM read bits by port | Nonconstant write enables by port |
| --- | ---: | --- | --- | --- |
| Candidate `k_memory` | 8,192 × 16 | 4 RAMB36E2 | B 16 | A 16 |
| Candidate `v_even` | 4,096 × 16 | 2 RAMB36E2 | B 16 | A 8 |
| Candidate `v_odd` | 4,096 × 16 | 2 RAMB36E2 | B 16 | A 8 |
| Control `k_memory` | 8,192 × 16 | 4 RAMB36E2 | B 16 | A 16 |
| Control `v_memory` | 8,192 × 16 | 4 RAMB36E2 | B 16 | A 16 |

Both arms have 32 KiB of logical cache data. The candidate splits its 16 KiB V half into two equal banks. Each mapped V bank has at least 16 read data connections and sits in the same PL0 clock domain. The directed RTL replay checks paired responses and scalar debug reads. The port columns count wired primitive pins, including depth cascades. Useful data width and capacity come from the RTL. The raw pin and property tables preserve actual BRAM widths, cascade settings, clocks and enable connections. These are static measurements.

The build reused the exact Experiment 22 control checkpoint and all 119 pinned shell inputs. The generated PS and neural port maps and the AXI address map match. Only `attention.sv`, `frontend.sv`, `kv_cache.sv`, `transformer.sv` had different supplied RTL bytes. The selected sites were `frontend.cache`, `transformer.att`. Both arms supplied the same 11 RTL filenames. The control used 8 files in the active hierarchy and the candidate used 8. The candidate supplied `fixed_scalar.sv`, `mac32.sv`, `dense.sv` unchanged, with no active instances of their modules. The legacy module declarations, public phase encoding, and complete AXI wrapper bytes match. Counts come from Vivado's routed hierarchical report. Some grouped LUTRAM and leaf entries in the raw census describe the same occupied resources.

The bounded remote flow took 1014.3 seconds, including image conversion and the mapped primitive census. Recovery verified all 340 archived members. The binary firmware matches the converted Xilinx payload and the program overlay names that image. Human attention and AI usage costs are unknown.

[Run record](run.json) · [RTL qualification](../attention-value-pair-v1-rtl-20261119T203052Z/findings.md) · [Experiment 22 route](../projections-read-ahead-v1-build-20261119T193229Z/findings.md) · [Protocol](../../experiments/kv260-attention-value-pair-v1.md)
