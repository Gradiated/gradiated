# Experiment 24 · Faster fabric clock

Compare the adopted [Experiment 23 circuit](../implementations/kv260/README.md#selected-circuit-comparison-baseline) at different PL0 clock rates on one KV260. Freeze the model, weights, two value lanes, precision, workload, software, supply settings and host timing boundaries. PL0 also clocks the accelerator’s AXI interface. Leave CPU, DDR and unrelated clocks at their original settings.

## Frequencies and expected result

The three proposed nominal rates are 50 MHz, about 52.5 MHz and 62.5 MHz. A previous Linux clock-tree capture reported a PL0 parent of 999,999,990 Hz. Divider products of 20, 19 and 16 therefore predict approximately 50.00, 52.63 and 62.50 MHz. Verify the actual Linux-configured rates, divider chain, parent and enable state at every change and measurement boundary. Cross-check the FPGA cycle counts against independently timed requests. Describe a Linux clock readback as a configured rate.

For identical FPGA cycles the expected device-time ratio is the control rate divided by the test rate. At the anticipated rates this means about 5% and 20% less device time than at 50 MHz. CPU admission and collection also take time. Complete-reply speed and gross module joules per token are empirical outcomes. Record the direction and size even if the energy difference is inconclusive.

The [measured Experiment 23 cycle counts](../results/attention-value-pair-20261119T234247Z-e21df0/run.json) give these device-time predictions. The CPU starts its request timer before it launches the FPGA. Report CPU-observed measurements separately.

| Prompt | FPGA completion cycles | 50 MHz | ≈52.63 MHz | 62.5 MHz |
| --- | ---: | ---: | ---: | ---: |
| Hello | 3,558,785 | 71.176 ms | 67.617 ms | 56.941 ms |
| Six bytes | 5,174,020 | 103.480 ms | 98.306 ms | 82.784 ms |
| 48 bytes | 8,760,172 | 175.203 ms | 166.443 ms | 140.163 ms |

## Implementation and physical qualification

Start by re-analysing the exact Experiment 23 routed checkpoint at each period. Check setup, hold, pulse width, clock and endpoint coverage, routing and diagnostics. An existing positive setup margin at 50 MHz is only an estimate of headroom. If the stretch target fails on that layout, retain the failure and allow one bounded, frequency-targeted implementation of the same logic. Prefer one qualified programming image across rates. A separately routed image needs its own 50 MHz control so a layout change cannot be counted as a frequency effect. Record the checkpoint, firmware, constraints, achieved timing and resource counts. Bound each implementation attempt to 45 minutes plus archive recovery. If a target still fails, keep the result as timing evidence and measure only the passing rates.

Use the [measurement standard](measurement-standard-v2.md) and the [Experiment 23 physical schedule](kv260-attention-value-pair-v1.md). For each qualified higher rate compare against a fresh matched 50 MHz control, with A/B/B/A observations, identical warm-ups and all mixed and per-prompt blocks. Verify frozen outputs, stop reasons and all three FPGA counter boundaries against the pinned reference. Compare TTFT, decode tokens/s, complete-reply time, module idle/active watts, gross joules per reply and per useful token, tokens/J, paired variation, temperature, sensor gaps and peripheral-clock activity. Report per-prompt and pooled results with their original timing and energy boundaries. Allow up to 30 minutes per physical comparison plus supervised restoration and verification. Stop on a rate mismatch, unrelated clock change, timing failure for that image/rate, output/counter mismatch or loss of reliable observation. Preserve partial evidence. Restore the original firmware, clock and weights, verify all 320 original BOS scores and confirm final ownership and peripheral state.
