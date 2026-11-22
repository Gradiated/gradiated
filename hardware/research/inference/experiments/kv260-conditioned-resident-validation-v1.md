# KV260 resident inference validation

**ID:** `kv260-conditioned-resident-validation-v1`

We want to know whether the board can retain one loaded model across independent text requests. Each later request starts after a context clear. If an earlier request affects any later score, the resident runner fails validation even when the chosen bytes still match.

## Fixed inputs and comparisons

Use `chip-joke-text-20261109` in the sealed W16A16 package `conditioned-6wbein7j` with manifest SHA-256 `b0394ba256d877fb62d6eb6e74942d5ff0c649cf751d53481e827c8bae5e9167`, the accepted KV260 revB and the same configured 50 MHz circuit. The original control and final restoration use the sealed `text-bgjxdjep` package. The tokenizer maps prompt bytes to two IDs per byte, preceded by BOS. Output selection takes the lowest ID with the highest signed integer score. Each request has context limit 256 and at most 255 output decisions including EOS.

The three prompts and expected completions are the same as those in the [fresh-load baseline](../results/speed-20261115T125210Z-f3c38c/run.json). Their frozen completion references have SHA-256 `33d290aed332af9e8b100a708222796d53f82529bb9c55d5d9ed13606cb0d367`. Compare every score, including generated positions, with the corresponding fresh-load trace.

| Case | Frozen prompt | Fresh-load trace | SHA-256 |
| --- | --- | --- | --- |
| A | `encoded-fu2p2q` | `timed-01-1/runner.stdout` | `9b23c8df5cb52633fe05bc02871d246e5538cb94a301aff756f37bfc7aa458ba` |
| B | `encoded-hello` | `timed-01-2/runner.stdout` | `e92f9d9d8ec33a6ccbfc715e42148a6aea441f017f89a931c08cad3a84197686` |
| C | `encoded-max48` | `timed-01-3/runner.stdout` | `1edfbd04efc45975a02cfec629601de65d430491313f93984a56a4f232ddb8a1` |

The traces belong to the earlier speed record's verified evidence manifest, SHA-256 `4c2ee0ba38efacf845a525f91af08429e65368c3fdc1e15c31f31e7ccfc3ba26`. Verify their case and prefix mapping before use. Use the sealed integer reference for the `repeated-J01-256` case.

## Procedure and acceptance

1. Use a fresh run ID and one named board owner. Check the reviewed configuration, boot, exclusive device access and absence of errors under the shared board lock. Pin the exact command, current source and reference packages. Run the original BOS control once and require all 320 scores and counters to match before proceeding.
2. Open one candidate native session. This resets the core and transfers the 29,281 model words. Require exactly one observed call to the sealed native begin function with counters `[0, 29281, 0, 0, 0]` and an empty context on entry. Keep the same session open for the entire schedule `A, B, A, A, C, B, C, B, repeated-J01-256, B`. It includes an immediate duplicate, an A–B–A replay, two long-to-short transitions and a short prompt after filling all 256 context positions.
3. Clear once before each later stage, for nine clears total. The separate clear command requires a configured, idle core. It sets context length to zero while retaining the weights. The new request begins at BOS. Require clear counters `[0, 29281, 0, 0, 0]`. Require all signed scores, counters, generated IDs, bytes and EOS to agree with their specified references. The board checks each stage, exports the evidence and waits for independent Mac verification before proceeding.
4. On success, close the candidate session, recheck health and restore the original model with one exact BOS check. Stop on any failure, unexpected state, timeout or missing comparison acknowledgement. Retain the first failed or incomplete gate for diagnosis and leave the board at its observed state.

Allow one supervised window of 600 seconds under a root-owned watchdog, with a 585-second internal deadline. The native calls retain their bounded deadline and the UART acknowledgements use the remaining session time. Keep the FPGA image, clock and boot firmware fixed. The board retains one active native session lock during the candidate sequence and the supervisor holds the advisory board lock through restoration and evidence export.

Capture monotonic timestamps around session construction, each clear and each inference. Record the first emitted byte and EOS for the completion requests. Hash and export scores outside those spans. Use Mac UTC for run chronology. This correctness run records per-request spans with validation gaps. It establishes no sustained-throughput, thermal or energy result. Keep raw traces, exact process outcomes and verification receipts in the ignored hardware runtime. Preserve an immutable run record after physical dispatch.
