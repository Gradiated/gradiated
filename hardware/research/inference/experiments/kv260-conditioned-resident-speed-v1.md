# KV260 resident-session speed

**ID:** `kv260-conditioned-resident-speed-v1`

What are the board-side request latency and back-to-back generation rate when the KV260 retains the model and clears only its context? We expect retaining the weights to remove the need to prepare and load a new session for each request. The [fresh-load baseline](../results/speed-20261115T125210Z-f3c38c/run.json) gives context for the result. Subtracting preparation from the earlier timing would miss the changed boundary, checks and inter-request work. Use a matched fresh arm under this harness if we later need to attribute a speedup.

## Fixed workload and admission

Use the [resident validation](../results/resident-20261115T143732Z-63263c/run.json) configuration and frozen W16A16 model `chip-joke-text-20261109`. Keep the exact sealed packages, 50 MHz FPGA image, 256-position context, hex input tokenizer, greedy lowest-ID tie break, EOS rule, batch size one and one active request. The three fixed prompts have 6, 5 and 48 input bytes and 122, 90 and 104 output bytes respectively. The [resident validation plan](kv260-conditioned-resident-validation-v1.md) pins their three full fresh-load raw score traces. Verify those pins and the original frozen prefix and completion checks before using those traces.

Hold the shared board lock from live preflight through health-checked original-model restoration. Require the reviewed boot, exclusive device access, 50 MHz clock and healthy original BOS control. Run three separately opened native reset/load sessions in the same supervisor process and boot. Require exactly one native begin per session, retaining its counters. Clear context before every request after the first in that session. Require exact zero-context counters, then begin at BOS. The process, hardware state and environmental conditions can be correlated across these sessions.

Each session runs six warm-ups, an observer pair for the 5-byte prompt and a 12-request timed block. Warm-ups use every prompt twice and are excluded from the measured summaries. Observer pairs alternate the optional per-output-byte timestamps off–on, on–off and off–on in the three sessions. They retain the same score capture and exact checks. Short blocks contain four appearances of each prompt per session, and each of the six possible three-prompt permutations occurs twice across the three short blocks. The last session adds a separate 48-request block with 16 appearances of each prompt. The sequence and any predecessor effects are identifiable from the frozen schedule. The long block describes one limited run in the final warmed session. A single boot supplies no reboot or day-to-day replication.

## Timing and evidence

Use board monotonic nanoseconds. Store session setup separately, then record these boundaries for every request.

| Marker | Boundary |
| --- | --- |
| Admission | Immediately before calling the resident completion routine, before prompt encoding or context clear |
| Context clear | Before and after the existing native clear call, when needed |
| Inference | Start after context admission. Timestamp the first emitted byte, subsequent emitted bytes in detailed mode, EOS and inference return |
| Completion return | After the runner hashes the frames and prepares the result |
| Verified finish | After exact score, output and context verification and construction of the compact receipt |

Report admission-to-first-byte and inference-start-to-first-byte separately. Subsequent byte intervals and decode rate use emitted bytes, with EOS timed as a decision that emits no byte. Report admission-to-EOS, admission-to-return and admission-to-verified-finish. Report emitted bytes per second and verified requests per second for each back-to-back block. Both use the interval from first admission to last verified finish. That interval includes hashes, exact checks, capture work, host overhead and gaps between requests. Hold health snapshots, JSON serialisation, UART export and Mac acknowledgement outside each block. Keep CPU policy, current-frequency and available thermal readings at the boundaries through the previously used read-only inventory. Compare known policy fields with the fresh-load baseline and record unavailable readings explicitly. Boundary samples cannot establish frequency or temperature throughout a block. Check paired timestamp overhead using admission-to-return and admission-to-verified-finish differences. Three pairs describe those checks only.

Before advancing to the next request, compare all 320 signed scores per frame, counters, token feedback, chosen bytes and EOS with the pinned fresh trace. Retain actual per-request frame digests, counters, decisions and timing. Export one full raw board exemplar for each prompt from the first warm-up block. These are observed digests for every request, exact board-side comparisons, and three independently recovered raw traces. A failure retains the first differing actual frame plus completed request receipts and stops further hardware requests. Cap each block at 48 requests, retaining compact records, at most three exemplars and one current raw request. Require Mac verification of each exported block before proceeding.

## Run window and reporting

Allow one 600-second root-owned watchdog with a 585-second inner deadline. The pre-launch staging transfer is bounded separately. Offline replay of the exact 108-request schedule with real captured frames produced about 2.26 MB of candidate UART exports. At 115200 baud this is about 196 seconds before transport overhead. Budget up to 240 seconds for all exports, 175 seconds for requests based on repeated verified fresh-load timings, and 100 seconds for setup, checks and control requests. Stop if the absolute deadline, any verification, clock, ownership or hardware-health check fails. Restore the original model with the same exact BOS check only after all gates pass and board health is confirmed. Keep the sealed firmware and FPGA setup fixed.

Preserve the exact source, invocation, pins, raw receipts and independent Mac checks. Summarise the short-block distributions by session and prompt, and the range of session summaries. Report the 48-request block separately. A byte token here is one output byte. These are verified board-side measurements with captures and checks, with no network service, thermal stability or energy claim.
