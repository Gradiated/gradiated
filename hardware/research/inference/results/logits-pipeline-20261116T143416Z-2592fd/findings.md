# Final token-score pipeline on the KV260

The candidate passed the exact-output gates and ran at the same 50 MHz as `scalar-div-v1`. Each arm used the same frozen model, request schedule, host and measurements. The three paired blocks reused the same board and boot. There were 36 verified timed requests and 18 warm-ups. The full-score diagnostics matched 139,840 signed scores. The original research circuit and pinned weights were restored, with all 320 original BOS scores verified.

## Speed

The table reports medians from six timed requests per arm for each prompt. One useful output token is one byte in this model.

| Prompt | Time to first token, ms | Decode, output tokens/s | Complete answer, ms |
| --- | ---: | ---: | ---: |
| Hello | 12.231 → 12.031 | 503.0 → 558.8 (+11.1%) | 191.607 → 173.551 (−9.4%) |
| Six-byte prompt | 14.477 → 14.299 | 460.0 → 506.3 (+10.0%) | 280.302 → 255.919 (−8.7%) |
| 48-byte prompt | 146.088 → 145.877 | 341.7 → 366.6 (+7.3%) | 450.983 → 430.138 (−4.6%) |

The board's first, last and terminal request counters matched simulation for all 36 timed requests. Scoring took 9,920 fewer cycles per retained position, equivalent to 0.1984 ms at 50 MHz. The pre-projection prefix had identical cycle counts in the matched RTL replay. That explains why the first token gained about 0.2 ms across all three prompts, while the complete answer gained more as the saving repeated. [Matched RTL replay](../logits-pipeline-rtl-20261116T125221Z-coverage/findings.md)

## Energy and circuit size

Gross VCC_SOM energy per verified answer fell **6.6–6.7%** across the three paired blocks, from an average of 0.964 J to 0.900 J. Gross energy per output token fell from 0.009156 J to 0.008546 J. Mean module-rail power was about 3.13 W in both arms. The energy window runs from first admission to final verification and includes the gaps between requests. The VCC_SOM sensor covers the module supply. This short comparison does not establish whole-board energy or long-run thermal behaviour.

The candidate routed with 14 additional LUTs and 11 additional registers. Chip-wide totals remained 30 DSPs and 36.5 block RAM tiles. The final scoring circuit still uses one multiply-and-accumulate lane. The earlier build attempt stopped at a stale Tcl source checksum and is preserved separately. [Routed implementation](../logits-pipeline-build-20261116T130030Z/findings.md)

[Run record](run.json) · [Independent audit manifest](audit-manifest.json) · [Experiment protocol](../../experiments/kv260-logits-pipeline-v1.md)
