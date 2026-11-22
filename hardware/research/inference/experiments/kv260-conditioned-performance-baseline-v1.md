# KV260 conditioned-model performance baseline

**ID:** kv260-conditioned-performance-baseline-v1

**Status:** Proposed. The timing runner and live power inventory have yet to be run. The [physical acceptance run](../results/physical-acceptance-20261114T232418Z-c39918/run.json) establishes correctness for the fixed cases. The question here is how long one request takes on the accepted KV260, and how much of that time is spent preparing the session, processing the input or generating later bytes.

## Fixed workload and controls

Use the same KV260 revB, sealed 50 MHz circuit, native host library and conditioned W16A16 model image as the physical acceptance run. Pin the full candidate manifest `b0394ba256d877fb62d6eb6e74942d5ff0c649cf751d53481e827c8bae5e9167`, the separate benchmark runner and its source patch. Batch size and concurrency are both one. Use a fresh session per request, including the same reset and full load of 29,281 model words. Keep the approved FPGA configuration intact. Record board and boot identity, kernel, PL0 readout, CPU governor and actual frequency policy, cooling, temperature and supply, attached peripherals and background activity.

Use the exact accepted UTF-8 prompts and expected output bytes from `completion-references.json`, SHA-256 `33d290aed332af9e8b100a708222796d53f82529bb9c55d5d9ed13606cb0d367`. Recover the 48-byte case from its pinned hexadecimal inputs.

| Case | Prompt bytes | Input positions including BOS | Expected output bytes before EOS |
| --- | ---: | ---: | ---: |
| encoded-fu2p2q | 6 | 13 | 122 |
| encoded-hello | 5 | 11 | 90 |
| encoded-max48 | 48 | 97 | 104 |

Each prompt byte becomes two input IDs. Every visible output byte takes one output ID. EOS is a separate decision and counts towards completion time, with zero emitted bytes. Use greedy first-index argmax over all 320 signed integer scores, the existing 255-decision cap and the 256-position context. Report the cases individually because prompt lengths and generated lengths differ. Output bytes/s on this model means byte tokens/s under this tokenizer, so retain both the unit and tokenizer for any comparison.

## Timing already available and the first runner change

The sealed [Python runner](../implementations/kv260/tools/board_bos.py) verifies packages and starts a fresh child for each completion. Native session initialisation resets the core and transfers the model. A native token call writes one token, polls, reads all 320 logits over AXI and checks completion. Python chooses the next ID. The native `CLOCK_MONOTONIC` readings enforce per-call deadlines. The ABI returns the API result, loaded word count, logit count, context length and saturation, with no timestamps or FPGA cycle count. The acceptance child elapsed time includes startup, validation and result handling and supplies no performance baseline. [Native adapter](../implementations/kv260/tools/board_bos.c), [host operations](../implementations/kv260/tools/host.c), [register map](../implementations/kv260/tools/host.h)

Use a small board-side Python runner kept separately from the sealed bundle. Reuse the sealed integrity checks, native calls, tokenisation and greedy/EOS rules. Retain the board-side watchdogs, exclusive session lock and clock/health checks. Add monotonic nanosecond timestamps and retain the values in memory. Buffer the returned frames for correctness checking, then hash, serialize and export them after the timed span. Keep Mac transport and gate review outside all board timings. Check observer overhead with the fixed `encoded-hello` prompt after warm-up. Run three pairs of fresh requests before the timed series. Pair one request with only the outer request-to-EOS timer and one with the same outer timer plus detailed per-step timestamps. Alternate which runs first in each pair. Keep the same capture and correctness checks in both modes and log all six runs within the 30-minute board window. Report each paired elapsed difference alongside the baseline. Use the recorded times for all latency and throughput figures. Performance results belong to the pinned benchmark runner, which differs from the accepted runner in its timing and capture path.

| Measurement | Boundary |
| --- | --- |
| Session preparation | Before to after native-session construction. Includes bundle and firmware checks, library and UIO setup, reset and model transfer. |
| Reset plus full model load | Around the existing `board_session_begin` call inside preparation. Includes native initialisation and AXI transfer. Timing pure model transfer separately would require a timestamp around `fpga_host_load_model`. |
| First output byte, fresh session | Before prompt encoding, after process launch, to the first non-EOS ID selected on the board. Includes preparing and loading the session. |
| First output byte, after loading | From session ready to first non-EOS selection. Includes processing every prefix position and choosing the first byte. Every request in this series has freshly loaded weights. A service that retains the weights and clears context between requests needs its own protocol. Subtracting load time from a fresh request does not measure that service. |
| Later output bytes | Store every output selection timestamp. Report per-request median later-byte interval and decode rate `(N − 1) / (t_last − t_first)` for N emitted bytes. |
| Completion and total rate | Before encoding to EOS selection, including the final score call and host argmax. Report `N / (t_EOS − t_request)` in output bytes/s. |
| Device-facing and host time | Bound each `NativeSession.step` call and Python's argmax separately, with prefix/decode phase and position. The call includes software overhead, AXI I/O, polling and FPGA compute. Report its span as measured. |

First-byte time is when the board selects a byte in memory. The existing program returns JSON at completion, so time to receive a streamed byte on a Mac needs a separate streaming protocol. A useful follow-up, only if needed, is to bracket the token write, first observed `LOGIT_VALID` and complete drain in the native host. Those intervals still include polling and AXI, and the last scores can be affected by host backpressure. Pure FPGA execution cycles would need an internal counter or independently aligned hardware trace. [AXI RTL](../implementations/kv260/rtl/axi_transformer.sv)

## Repetition, correctness and reporting

1. Under one board window, verify the sealed configuration and candidate payloads. Run one equivalence check of the benchmark runner against the seven accepted vector digests and three accepted completions before timing. Require the same output IDs, EOS, counters and no saturation. Keep the integer model and clock fixed.
2. Warm up with two untimed complete requests per prompt. Run the six observer-check requests, then collect ten timed requests per prompt, rotating the three-case order each round. Warm-up refers to the machine's operating state. Each timed request still starts with a fresh model load. Cap the supervised board window at 30 minutes and each completion at 180 seconds. Preserve metadata and partial results and stop on the first timeout, correctness mismatch, board fault or unsafe drift.
3. After each timed span, verify prefix logits, frame counters, independently calculated decisions, output bytes and EOS against the frozen inputs. Keep all raw samples, including failures, alongside capture and reference hashes. Record temperature and frequency before and after each round if exposed. Unknown readings stay unknown. Repeat the same protocol in a separate session before treating an observed difference as a reproducible improvement.
4. Report per-case medians, interquartile ranges, min/max and the count of valid requests. Summarize later-byte intervals within requests first so long outputs do not dominate. Ten requests are descriptive and do not establish tail SLOs. Keep timing clock resolution, paired observer checks and any temperature or scheduling drift in the record.

## Power and energy are separate measurements

AMD documents the carrier's INA260 at I²C address `0x40` on `VCC_SOM`, the 5 V SOM supply. Our archived device tree also lists `ina260-u14` and an `iio-hwmon` mapping. That identifies a candidate measurement point. The live driver, exposed channels, scaling, read permissions, conversion and averaging period, effective update rate and sampling overhead have yet to be checked. Faster polling cannot create new sensor conversions. Sampling that rail would report SOM-supply energy. Any channel inventory should start with reads from the exposed driver and preserve its configuration. [AMD DS986 power specification](https://docs.amd.com/r/en-US/ds986-kv260-starter-kit/Power-and-Electrical), [TI INA260 data sheet](https://www.ti.com/lit/ds/symlink/ina260.pdf)

For a whole-board result, identify an available logging DC meter or power analyser at the 12 V board input and verify its rating, resolution, acquisition interval and averaging, calibration or stated accuracy, and timestamp/export capability. Record the supply, fan, peripherals and every power path, including the USB UART. The 12 V trace represents the board input only if any separately supplied path is accounted for. An AC wall meter includes adapter losses and defines a different boundary. The acceptance records identify no available meter and contain no live power samples. [AMD board connections](https://docs.amd.com/r/en-US/ug1089-kv260-starter-kit/Interfaces)

Align power and request markers, measure the alignment error and log actual timestamps. Measure stable configured idle before and after each active block with the same peripherals and logging. Repeat at least three paired blocks. If the instrument is slow, use blocks of consecutive requests with enough independent samples and record the block's actual duty cycle, including any gaps and reloads. Integrate the active trace for gross joules. Also report incremental joules after subtracting the matched idle integral over the same window. Preserve meter accuracy, sample loss or repeats, baseline variation and between-block spread. Call a difference unresolved if drift, timing uncertainty or resolution is comparable to it. Report aggregate joules per emitted byte only when energy, block window and completed output count share the same boundary. A slow trace cannot resolve energy for an individual token.

The next implementation step is the minimal timing runner and an equivalence check on the preserved fixtures. A separate energy pass depends on identifying the live SOM readout or an available input meter with a usable timebase. This plan specifies no purchases or new board configuration.
