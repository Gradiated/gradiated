# KV260 resident inference with and without power logging

**ID:** `kv260-conditioned-logger-comparison-v1`

Does the 20 Hz INA260 logger change measured inference performance enough to affect comparisons? Three paired measurements screen for a practical effect. The logged arms can also give gross and matched-idle-adjusted energy through the **VCC_SOM supply** over a complete verified block. The sensor boundary differs from the 12 V starter-kit input.

## Fixed controls

Reuse the resident-speed packages, platform, request and verification contract. Use `chip-joke-text-20261109`, W16A16, 50 MHz, the exact three frozen prompt traces, greedy selection, output byte tokens and one request at a time. Check all 320 scores in each frame, the output bytes, EOS and counters. Use the same per-byte timing and verification work in both arms.

Use three resident sessions in one boot, one per pair. Each pair has two arms in order off/on, on/off, off/on. Warm up with six verified requests per arm, two of each prompt. Run twelve consecutive verified requests per measured arm, four of each prompt, for 1,264 output bytes. The two arms in a pair have exactly the same order. Rotate the short order so its last prompt matches the last warm-up prompt. Both idle windows retain the same completed context for that prompt, as verified by the full completion receipts. The first active request includes the normal resident context clear. Both idle windows last two seconds, with a half-second guard between idle and active work. This creates matching measurement windows without establishing thermal equilibrium. Export evidence only after the arm.

## Sensor, boundaries and decisions

Start the unprivileged sampler in a separate process before the settling period. Keep CPU affinity and priorities unchanged. Read the selected INA260 power channel once per absolute 50 ms slot, up to 350 slots. Record read start and end on the same board monotonic clock used by the inference runner. Skip slots whose start is at least 25 ms late. Keep all missed-slot and error evidence. Sensor identity, scale, settings and disabled buffer must match before and after. The sampler uses a 24-second watchdog and the board supervisor reaps the child. Both arms use the fixed 17.5-second measurement window and matching guards.

Use block throughput and within-prompt median admission-to-first-byte and admission-to-verified-finish latency. Report all signed on/off differences. A metric stays within the predeclared practical screen only if every paired difference is within ±2%. A change beyond that screen is a reason to investigate observer effects. A result inside it describes these three pairs, with no statistical equivalence claim. A crashed sampler invalidates its arm. A valid arm with inadequate power coverage may still contribute to timing.

Integrate power from first admission to last verified finish. The IIO count converts to 10 mW per count. Use the trapezoid rule with endpoints clipped at the boundary. Require samples bracketing all three windows and no intervening gap above 75 ms. Compare read midpoints with read-start and read-end estimates and midpoint timestamps shifted by ±50 ms as a sensitivity test. These shifts are scenarios, not confidence bounds or direct measurements of sensor age. Retain all admitted block values. Report gross joules per block, per verified completion and per output byte. Subtract active duration multiplied by the mean of the two idle powers for the separate incremental estimate. Report the two idle powers and retain negative estimates. Treat small differences as unresolved when drift, alignment sensitivity or instrument uncertainty is comparable. The 10 mW step is the reporting increment. The logger’s process CPU time excludes some kernel overhead.

## Run and ownership

One owner and one shared hardware lock. Reuse the resident harness’s live boot, clock, firmware, state and exact original BOS checks. Reuse the existing health-gated restoration with the original weights. Keep the FPGA image and firmware unchanged. Cap staging at 90 seconds and execution at 600 seconds with a 585-second inner deadline. Stop when a live gate fails. Preserve both waiting and execution failures and any acquired raw evidence on the Mac. Keep staged sources, exact commands, raw power reads, request receipts, score digests and restoration checks pinned. No site changes or publication are part of this trial.
