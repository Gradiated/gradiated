# Sharing the exact normalization multiplier

The comparison completed all 200 timed replies on one KV260 at 50 MHz. Median completion changed -0.02% to +0.01% across the three fixed prompts. Pooled mixed-block gross VCC_SOM joules per verified answer changed +0.06%. The routed blocks and both arms' replay pins are available in the [routed build](../norm-mul-shared-v1-build-20261119T181925Z/findings.md) and [exact RTL qualification](../norm-mul-shared-v1-rtl-20261119T175457Z/findings.md).

Routed DSP use changed from 89 to 57. The first, last and completion FPGA clocks matched exactly.

## Request timing

The board CPU starts timing before request encoding and context clear. Decode rate uses the intervals between useful bytes. Completion includes stopping and drain. Each arm contributed eight mixed-block observations per prompt. The range is the min/max of four round-paired median changes.

| Prompt | First useful byte, ms | Decode, tokens/s | Completion, ms | Paired completion change |
| --- | ---: | ---: | ---: | ---: |
| Hello | 6.835 → 6.817 (-0.26%) | 1187.3 → 1187.3 (-0.00%) | 82.827 → 82.809 (-0.02%) | -0.03% to +0.01% |
| Six-byte prompt | 8.072 → 8.074 (+0.02%) | 1088.3 → 1088.3 (-0.00%) | 120.431 → 120.433 (+0.00%) | -0.01% to +0.02% |
| 48-byte prompt | 76.108 → 76.119 (+0.01%) | 809.4 → 809.4 (-0.00%) | 204.826 → 204.838 (+0.01%) | +0.00% to +0.01% |

Across the 12 prompt-by-round pairs, CPU completion changed −0.034% to +0.022%, first-byte latency changed −0.409% to +0.333%, and decode changed by less than 0.001% in either direction. The paired measurements leave a host timing effect unresolved.

## Exact work and FPGA clocks

The three natural prompts reached EOS with the same output bytes in both arms. Each timed reply, warm-up and smoke was checked against its own replay first, last and completion clocks.

| Prompt | Encoded input tokens | Useful output tokens | Positions | Scored positions | First | Last | Done | Done clocks saved |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Hello | 11 | 90 | 101 | 91 | 329,533 → 329,533 | 4,077,439 → 4,077,439 | 4,129,132 → 4,129,132 | 0 |
| Six-byte prompt | 13 | 122 | 135 | 123 | 391,907 → 391,907 | 5,950,820 → 5,950,820 | 6,009,805 → 6,009,805 | 0 |
| 48-byte prompt | 97 | 104 | 201 | 105 | 3,780,951 → 3,780,951 | 10,143,776 → 10,143,776 | 10,216,819 → 10,216,819 | 0 |

The three normalization stages take turns using the shared multiplier. Both routed images took exactly the same first, last and completion FPGA clocks for all three natural prompts. The resource comparison reflects that matched work.

## Gross VCC_SOM energy

The INA260 trace integrates the active block from first admission through final exact verification, including gaps between replies. Idle power averages equal settled brackets with the same loaded weights and context count. Gross ratios pool joules and their matching work totals.

| Scope | Arm | Active W | Idle W | Gross J/answer | Gross J/token | Tokens/J |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | Dedicated normalization multipliers | 3.1104 | 3.0131 | 0.425275 | 0.00403742 | 247.68 |
| Mixed | Shared normalization multiplier | 3.1123 | 3.0154 | 0.425547 | 0.00404000 | 247.52 |
| Hello | Dedicated normalization multipliers | 3.1063 | 3.0157 | 0.258974 | 0.00287749 | 347.53 |
| Hello | Shared normalization multiplier | 3.1105 | 3.0144 | 0.259317 | 0.00288130 | 347.07 |
| Six-byte prompt | Dedicated normalization multipliers | 3.1105 | 3.0120 | 0.376751 | 0.00308812 | 323.82 |
| Six-byte prompt | Shared normalization multiplier | 3.1099 | 3.0149 | 0.376637 | 0.00308719 | 323.92 |
| 48-byte prompt | Dedicated normalization multipliers | 3.1102 | 3.0193 | 0.639279 | 0.00614691 | 162.68 |
| 48-byte prompt | Shared normalization multiplier | 3.1116 | 3.0156 | 0.639502 | 0.00614906 | 162.63 |

Each alignment cell reports the range of paired gross J/answer changes. Mixed has four pairs, and each fixed-prompt block has two.

| Scope | Midpoint | Midpoint −50 ms | Midpoint +50 ms | Read end | Read start |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mixed | -0.48% to +0.80% | -0.49% to +0.56% | -0.47% to +0.81% | -0.48% to +0.80% | -0.48% to +0.80% |
| Hello | +0.03% to +0.24% | +0.01% to +0.25% | +0.03% to +0.25% | +0.03% to +0.24% | +0.03% to +0.24% |
| Six-byte prompt | -0.29% to +0.23% | -0.30% to +0.24% | -0.27% to +0.26% | -0.29% to +0.23% | -0.29% to +0.23% |
| 48-byte prompt | +0.00% to +0.07% | -0.03% to +0.18% | +0.03% to +0.08% | +0.00% to +0.07% | +0.00% to +0.07% |

The 20 Hz sampler skipped 0 scheduled slots. Every integration used the same 75 ms limit on the gap between contributing samples. SPI1 or TPM counters changed in `homogeneous-p1-encoded-hello-candidate` +1349 ms SPI1, +0 TPM transfers. The brackets cannot resolve activity inside the integration window.

SPI1 and TPM counters stayed steady in all four mixed pairs. Across those pairs and all sample alignments, gross energy per answer changed −0.49% to +0.81%. That variation leaves the pooled +0.06% module-energy difference unresolved.

Active-block temperature brackets showed ams/temp1 25.4 → 25.8 °C (peak 27.1 °C), ams/temp2 26.1 → 26.4 °C (peak 27.4 °C), ams/temp3 24.2 → 24.1 °C (peak 24.6 °C).

## Routing and restoration

| Routed resource | Dedicated normalization multipliers | Shared normalization multiplier | Change |
| --- | ---: | ---: | ---: |
| LUTs | 39,132 (33.41%) | 38,130 (32.56%) | -1,002 |
| Registers | 16,492 (7.04%) | 15,605 (6.66%) | -887 |
| DSPs | 89 (7.13%) | 57 (4.57%) | -32 |
| Block RAM tiles | 39 (27.08%) | 39 (27.08%) | +0 |
| Setup slack, ns | 4.069 | 5.418 | +1.349 |
| Hold slack, ns | 0.011 | 0.017 | +0.006 |

| Routed hierarchy | LUTs | Registers | DSPs | Block RAM tiles |
| --- | ---: | ---: | ---: | ---: |
| First normalization | 6,537 → 5,964 | 2,185 → 1,674 | 16 → 0 | 1 → 1 |
| Second normalization | 6,525 → 5,939 | 2,185 → 1,675 | 16 → 0 | 1 → 1 |
| Final normalization | 6,537 → 5,907 | 2,185 → 1,676 | 16 → 0 | 1 → 1 |

Both images use on-chip weights and the same model upload of 117,124 bytes. The allocated KV cache is 32,768 bytes. Valid KV contents reached 12,928, 17,280 and 25,728 bytes respectively. [Logical storage accounting](../../implementations/kv260/resource-memory-baseline.md)

The board ran ABBA across three comparison image loads. Nine smoke replies and 36 warm-ups passed. The original image, original weights and all 320 original BOS scores passed restoration on the same boot. Original UIO permissions, clock, firmware and overlay identities were verified.

[Run record](run.json) · [Protocol](../../experiments/kv260-norm-mul-shared-v1.md)
