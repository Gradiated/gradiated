# Routed DDR4 score-buffer comparison at 50 MHz

Both Vivado 2025.2 routes close setup and hold at 20 ns on the K26. The prefetch circuit retains the eight BRAM tiles recovered in Experiment 16. It maps no BRAM or URAM in the logits lanes or group reader. The input embedding table still occupies six RAMB36E2 and one RAMB18E2.

| Routed quantity | Serialized DDR4 | Prefetch DDR4 | Difference |
| --- | ---: | ---: | ---: |
| FPGA LUTs | 38,978 | 39,050 | +72 |
| FPGA registers | 14,844 | 14,850 | +6 |
| FPGA DSPs | 41 | 41 | 0 |
| FPGA BRAM tiles | 31 | 31 | 0 |
| Accelerator LUTs | 38,394 | 38,465 | +71 |
| Accelerator registers | 14,134 | 14,140 | +6 |
| Logits LUTs | 1,217 | 1,215 | -2 |
| Logits registers | 667 | 667 | 0 |
| Logits DSPs | 8 | 8 | 0 |
| Group reader LUTs | 302 | 394 | +92 |
| Group reader LUTRAM LUTs | 80 | 148 | +68 |
| Group reader logic LUTs | 222 | 246 | +24 |
| Group reader registers | 73 | 79 | +6 |
| Group buffer bytes | 512 | 1,024 | +512 |
| Setup slack | +5.215 ns | +4.424 ns | -0.791 ns |
| Hold slack | +0.012 ns | +0.020 ns | +0.008 ns |

The serialized reader has two 32×64-bit staging memories, one for each half of a coordinate’s eight weights. The prefetch reader deepens both to 64×64 bits and uses the high address bit to select the 512-byte slot. The two logical slots share those physical memories, so their LUTRAM cost is measured together.

| Staging memory | Serialized primitives | Prefetch primitives |
| --- | --- | --- |
| Low 64-bit half | 5 RAM32M16, 70 RAMD32, 10 RAMS32 | 9 RAM64M8, 1 RAM64X1D, 74 RAMD64E |
| High 64-bit half | 5 RAM32M16, 70 RAMD32, 10 RAMS32 | 9 RAM64M8, 1 RAM64X1D, 74 RAMD64E |

The census includes memory containers and their leaf primitives. The utilization table gives the actual mapped LUT count.

The candidate uses the same native read-only 64-bit HP0 connection, unremapped low DDR and eight-beat incrementing bursts at PL0. Generated PS writes and the interface, AFI restoration and direct-DMA overlays match the serialized build. Both reports show complete placement and routing, zero unconstrained internal endpoints, and zero design-rule errors or critical warnings.

The candidate package matches the full recovered 389-file archive and the frozen paired RTL replay. The Mac verified every archive member and both programming packages before the board run. These figures measure routed resources and timing closure. Physical service latency, inference time and module energy are recorded separately.

[Run record](run.json) · [Artifact manifest](audit-manifest.json) · [Serialized control route](../logits-ddr4-burst-build-20261119T115915Z/findings.md)
