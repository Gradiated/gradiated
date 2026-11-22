# Paired attention exponential implementation

The candidate met the 50 MHz constraint. Routed worst setup and hold slack were 5.544 ns and 0.012 ns.

| Resource | Adopted control | Candidate | Change |
| --- | ---: | ---: | ---: |
| LUTs | 34516 | 38329 | +3813 |
| Registers | 13581 | 14464 | +883 |
| DSPs | 37 | 41 | +4 |
| Block RAM tiles | 38 | 39 | +1 |

The existing score buffer still has one read port in the RTL. Each exponential unit has a local table with 257 entries of 32 bits. Both copies are loaded together. The extra logical table holds 1,028 bytes.

The checked route identifies the following named memory and DSP cells. Grouped LUTRAM macros and their leaf primitives can refer to the same occupied resources.

- candidate, primary scalar — 4 DSP48E2, 2 RAMB18E2.
- candidate, second exponential — 4 DSP48E2, 2 RAMB18E2.
- candidate, whole attention — 9 DSP48E2, 48 RAM256X1S, 1 RAM32M16, 2 RAM32X1D, 20 RAM64M8, 4 RAMB18E2, 18 RAMD32, 160 RAMD64E, 2 RAMS32, 192 RAMS64E.
- control, primary scalar — 4 DSP48E2, 2 RAMB18E2.
- control, whole attention — 5 DSP48E2, 80 RAM256X1S, 1 RAM32M16, 2 RAM32X1D, 2 RAMB18E2, 18 RAMD32, 2 RAMS32, 320 RAMS64E.

The shared exponential result buffer retained the control's RAM mapping (32 RAM256X1S, 128 RAMS64E). The score buffer uses one read port in both designs. Vivado mapped the control score buffer to 32 RAM256X1S, 128 RAMS64E and the candidate score buffer to 20 RAM64M8, 160 RAMD64E. The routed resource difference includes this change and the control logic for issuing and retiring pairs.

0 named memory or DSP census rows differed outside the attention hierarchy. The source manifests preserve all unrelated RTL.

[Run record](run.json) · [RTL comparison](../attention-exp-pair-v2-rtl-20261117T230104Z/findings.md) · [Protocol](../../experiments/kv260-attention-exp-pair-v2.md)
