# KV260 observation counters v1

Status: offline build completed on 15 November 2026 after resuming from the verified placed checkpoint. Simulation, routing, timing, clock coverage, DRC and programming-file preparation passed. The complete build is checksum-verified on the Mac, with the interrupted route preserved. [Offline build findings](../results/observer-build-20261115T180508Z/findings.md). No observer programming has occurred, and physical qualification still requires explicit approval. [Resume handoff](kv260-steps-1-3-handoff.md). User-authorised roadmap step 3 only. No optimisation campaign is authorised by this protocol.

## Question and bounds

Can a separately identified circuit expose useful stage and handshake measurements while preserving the frozen chip-joke-text-20261109 W16A16 model's outputs and quantifying the cost of observation against the original bitstream?

Keep the original RTL, model, weights, golden references, firmware and previous run records unchanged. Generate a derivative from SHA-256-pinned source. Retain failed attempts. One instrumented implementation, no clock, arithmetic, memory-placement, parallelism or PS-interface changes. Build on the already-running temporary Linux host, maximum two Vivado threads, 180 seconds each for generate/reports/bitstream and 600 seconds each for synthesis/optimise/place/route. At most two narrowly corrected retries for preparation/tool failures. Copy all unique inputs, reports and accepted artifacts back to the Mac with verified SHA-256 hashes. No server-only evidence, purchases or infrastructure changes.

## Measurement contract

The original circuit runs at 50 MHz. All counters are 32-bit saturating unsigned values with sticky overflow flags. Clear them with the existing accepted context-clear command, board reset or soft reset. A request can span several tokens, accumulating counts until the next context clear. After a completed request, one owner reads idle snapshots outside the timed inference interval. Concurrent token submission, clear or reset makes a counter read invalid. No extra control registers or feedback into arithmetic are introduced.

Registers: 0x24 returns observation ABI KV01 (0x4b563031), 0x28 gives busy bit0 and any-overflow bit1, 0x2c returns the overflow mask, and 0x40–0xbc return counters 0–31. Data/overflow reads during activity or simultaneous control commands return SLVERR. Observation registers are read-only. Invalid and unaligned legacy addresses remain errors.

| Counters | Meaning |
| --- | --- |
| 0 | Core busy cycles |
| 1–19 | Busy cycles in each transformer phase, following the frozen RTL enum |
| 20 | Accepted input tokens |
| 21 | Accepted score transfers |
| 22 | Score-valid cycles without accepted score transfer |
| 23 | Cache request valid, not ready, while core busy |
| 24 | Attention in cache-response states without valid cache data |
| 25 | Accepted cache-pair transfers |
| 26 | Feed-forward pair state without both gate/up values available |
| 27 | Feed-forward scalar region, including control and handshake cycles |
| 28 | Feed-forward down-projection start/run region |
| 29 | Reserved, zero |
| 30 | Accepted AXI read addresses while core busy |
| 31 | Executed AXI writes while core busy |

Only phases 1–19 partition busy cycles. Other counters overlap those phases and one another. Score stalls include software polling and bus response delays. Cache counters do not measure external DDR bandwidth. Wait counters detect additional bubbles, so zero waits do not imply zero memory-access cost. For N completed tokens from context clear, the frozen schedule should accept 32*N*(N+1) cache-pair transfers. Scalar-region cycles are not pure arithmetic cycles. Idle time between tokens and CPU argmax lies outside core busy. Convert cycles to time only with a verified clock. Reject overflowed values for exact decomposition.

## Acceptance and physical qualification

Before programming: verify pinned source and simulator; lint; real-core golden-score simulation; cycle-identical original/variant bus traces under identical stimulus; synthetic AXI tests for busy-read refusal, concurrent reset/read, saturation, overflow and reset; full-device Vivado source closure, 50 MHz clock/reset topology, timing, routing and DRC gates. No waivers.

On the board: SOL is sole operator. Pin the new bitstream separately, preserve and verify restoration of the original firmware. Keep the original firmware file untouched. Use separately named observer firmware and overlay, with an explicitly pinned host identity-check derivative that accepts only that variant. Record every firmware switch, and restore the original firmware after the last observer arm. Use the frozen three prompts, exact per-position score and completion checks, unchanged resident host wrapper and native library. After the first original control arm, perform a three-prompt functional/counter smoke test on the observer firmware before its matched warmup, with counter reads after request completion. Verify phase sum, token/score counts, stable snapshots and no overflow. Reject changed outputs, errors, clock changes or failed restoration.

Then qualify perturbation against the original firmware with matched 20 Hz VCC_SOM logging and idle windows. Use three original/observer paired blocks in AB/BA/AB order, two repetitions of each frozen prompt per arm, three warmups per arm: 36 scored and 18 warmup requests. Capture counters for the final request of each observer arm only after the sampler has exited and the full active and matched idle windows have closed. Do not insert counter reads between scored requests. Rotate the final prompt across pairs to cover all three prompts. These reads cannot contaminate either individual request or whole-block timing and energy. Use a fresh resident session per arm for both firmware variants, loading outside the timed window. The healthy sequence has four programming switches: original to observer, observer to original, original to observer, then restore original. Report request timing, variation, module energy and utilisation deltas. A 2% timing screen is descriptive, not proof of equivalence or statistical significance. If any pair exceeds it, preserve the result and do not treat the variant as timing-neutral. Report power resolution and sampling limitations even if differences are small. No switch-on/off-only substitute for the original-bitstream comparison.

Stop before roadmap step 4. Review results with the user before choosing any circuit optimisation experiments.
