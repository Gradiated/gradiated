# Paired attention exponential implementation

The candidate met the 50 MHz constraint. Routed worst setup and hold slack were 3.658 ns and 0.012 ns.

| Resource | Adopted control | Candidate | Change |
| --- | ---: | ---: | ---: |
| LUTs | 34516 | 41324 | +6808 |
| Registers | 13581 | 22702 | +9121 |
| DSPs | 37 | 41 | +4 |
| Block RAM tiles | 38 | 39 | +1 |

The existing score buffer still has one read port in the RTL. Each exponential unit has a local table with 257 entries of 32 bits. Both copies are loaded together. The extra logical table holds 1,028 bytes.

The checked route identifies the following named memory and DSP cells. Grouped LUTRAM macros and their leaf primitives can refer to the same occupied resources.

- candidate, primary scalar — 4 DSP48E2, 2 RAMB18E2.
- candidate, second exponential — 4 DSP48E2, 2 RAMB18E2.
- candidate, whole attention — 9 DSP48E2, 16 RAM256X1S, 1 RAM32M16, 2 RAM32X1D, 20 RAM64M8, 4 RAMB18E2, 18 RAMD32, 160 RAMD64E, 2 RAMS32, 64 RAMS64E.
- control, primary scalar — 4 DSP48E2, 2 RAMB18E2.
- control, whole attention — 5 DSP48E2, 80 RAM256X1S, 1 RAM32M16, 2 RAM32X1D, 2 RAMB18E2, 18 RAMD32, 2 RAMS32, 320 RAMS64E.

This routed attempt was withheld from the board comparison. The focused checkpoint query identifies 8,192 FDRE cells in the 256 × 32 exponential result buffer. The control maps that buffer to 32 RAM256X1S macros, each with four RAMS64E leaves. The two write sites in the source presented the logical single stream in a form that led Vivado to expand the buffer. The single-write retry is recorded separately.

0 named memory or DSP census rows differed outside the attention hierarchy. The source manifests preserve all unrelated RTL.

[Run record](run.json) · [RTL comparison](../attention-exp-pair-rtl-20261117T224037Z/findings.md) · [Protocol](../../experiments/kv260-attention-exp-pair-v1.md)
