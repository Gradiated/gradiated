# Experiment 15 · Read four weights at a time and burst a complete row from DDR4

Compare three ways to read the same 2 KiB attention output matrix through the K26 module's HP0 port. [Experiment 14](../results/output-projection-ddr4-20261118T232351Z-c820f6/findings.md) observed 13.46 extra clocks per serial weight on this workload. It used one of four signed weights returned with each AXI beat. Test how much waiting comes from repeatedly fetching the same beat, then how much remains when adjacent beats share one address request.

## Controls and interpretation

Use the frozen conditioned W16A16 transformer, exact bank-4 weights, fixed clock (50 MHz), same multiply and accumulation order and the three historical prompts. Switch modes only when idle. One routed image contains all four paths. A is the BRAM reference, B reproduces the Experiment 14 single-weight read, C retains four weights from one aligned beat, and D fetches the entire 32-weight row in one eight-beat burst. Consume each row in original order. Issue no speculative request for the next row. Verify bytewise against the frozen model and check the BRAM request cycles against Experiment 13. Per-run board waits may vary.

| Mode | Accepted address requests per 32 × 32 projection | Returned 64-bit beats | Bytes at HP0 | Useful weight bytes in arithmetic |
| --- | ---: | ---: | ---: | ---: |
| A · BRAM | 0 | 0 | 0 | 2,048 |
| B · One DDR4 weight | 1,024 | 1,024 | 8,192 | 2,048 |
| C · Four DDR4 weights | 256 | 256 | 2,048 | 2,048 |
| D · DDR4 row burst | 32 | 256 | 2,048 | 2,048 |

B versus C tests reuse of returned data. C versus D holds useful bytes and returned bytes fixed and tests row buffering and issuing a burst. Local buffer latency can offset the saved requests. Report actual stage and whole-request cycles and reconcile the difference with the instrumented waits. Actual DDR chip commands, sustained bandwidth and off-module energy are outside these measurements. The combined route reports the cost of the measurement circuit. Treat per-mode area savings as unmeasured.

## Qualification and schedule

First replay the frozen RTL cases, packing and signed lane order, destination rows, invalid/error responses, backpressure, and reset/drain cases, including row boundaries and the last valid buffer address. Verify the functional and physical transfer totals independently. Use a bounded two-job Vivado build, verify a 20 ns constraint with setup and hold passing, routed read-only HP0, burst length, sequential 64-bit beats, address containment in the reviewed buffer, AFI configuration and unchanged reset/clock. Preserve unsuccessful development attempts. Budget 45 minutes for a route plus five minutes for recovery, and 25 minutes for one full RTL replay. Freeze actual sources, artifact hashes, device/boot details and an invocation before physical execution.

Run one untimed smoke reply per mode and prompt (12 replies). From the slowest smoke derive a shared per-request timeout, three times the longest rounded up to seconds with a one-second floor and a 30-second ceiling. For each mixed block, use the historical three warm-ups and six timed replies, two per prompt. Cycle the run orders A B D C, B C A D, C D B A and D A C B. Balance prompt order using the historical schedule; repeat its first prompt permutation in the fourth group. Each mode provides eight measured samples per prompt. Keep start and end idle context matched within each block.

Then measure each prompt alone, with one warm-up and 18 timed Hello, 12 six-byte or eight 48-byte replies per block. First pass: Hello A B D C, six-byte B C A D, 48-byte C D B A. Second pass: reverse prompt order and each prompt's mode order. The experiment contains 40 powered blocks, 400 timed replies and 72 warm-ups, plus the 12 smokes. Use a 35-minute board supervisor deadline and reserve a separate three minutes for restoration. Transfer and recovery have separate bounds.

Use the [standard measurement sheet](measurement-standard-v2.md). Record board-side TTFT, decode tokens/s, complete reply time, output counts, FPGA cycles, weight reads/beats, useful bytes, read wait, timing variation, setup, routed resources and sampled temperatures. Measure gross VCC_SOM module energy in matched verified-workload and idle windows with SPI1/TPM brackets. Report mixed and per-prompt J/answer and J/output token, tokens/J, active/idle W and sampling alignment sensitivity. Preserve each individual block. Verify reference output and stop reason on every request. Stop on an FPGA fault, incorrect output, invalid counts or unsafe memory release.

Use the previously qualified, temporarily loaded Linux driver design, updated for the new mode register. Map only the checked aligned, privately owned buffer. Retain its ownership until all AXI reads have drained. Restore and verify the original research image, weights, HP0 settings and all 320 original BOS scores. Leave the verified board running. Save raw inputs, runs and hashes on the Mac and add separate build, RTL and board results to the research index.
