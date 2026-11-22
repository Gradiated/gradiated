# KV260 intermediate prompt score skipping

One physical KV260 at the same reported 50 MHz ran the frozen W16A16 model with two control paths. Both arms used the same autonomous host reader. The candidate omitted the vocabulary projection before the final prompt position. The full prompt and KV cache were processed in both arms, and every decode projection was retained.

The candidate matched 139,840 signed scores in separate full-score diagnostics. All compact completions, their stops and context counts matched. The one-byte and zero-byte caps passed. The original firmware and pinned weights were restored and the original 320 BOS scores matched. Full weight-memory readback was outside the test.

## Request timing

Each table entry is the median of two requests for that prompt and arm. Time starts before prompt preparation and context clear. The CPU timestamps each usable output byte. Decode rate divides the number of output bytes after the first by the time between first and last output. Completion includes stop handling and final output drain. Post-request checks are timed separately.

| Pair | Prompt | First byte, Full scoring / Skipped prompt scores (ms) | Decode, Full scoring / Skipped prompt scores (bytes/s) | Completion, Full scoring / Skipped prompt scores (ms) |
| --- | --- | ---: | ---: | ---: |
| 1 | `encoded-fu2p2q` | 33.06 / 27.99 | 273.30 / 273.30 | 480.52 / 475.45 |
| 1 | `encoded-hello` | 27.73 / 23.49 | 298.48 / 298.48 | 330.02 / 325.78 |
| 1 | `encoded-max48` | 314.50 / 273.96 | 204.12 / 204.12 | 824.97 / 784.42 |
| 2 | `encoded-hello` | 27.86 / 23.62 | 298.48 / 298.48 | 330.15 / 325.91 |
| 2 | `encoded-max48` | 314.52 / 273.96 | 204.12 / 204.12 | 824.98 / 784.42 |
| 2 | `encoded-fu2p2q` | 32.96 / 27.86 | 273.30 / 273.30 | 480.42 / 475.33 |
| 3 | `encoded-max48` | 314.67 / 274.13 | 204.12 / 204.12 | 825.13 / 784.60 |
| 3 | `encoded-fu2p2q` | 32.94 / 27.87 | 273.30 / 273.30 | 480.40 / 475.33 |
| 3 | `encoded-hello` | 27.72 / 23.50 | 298.48 / 298.48 | 330.01 / 325.80 |

Relative change is the candidate divided by the control, minus one. Ranges below cover the three paired medians.

| Prompt | First-byte time | Decode rate | Completion time |
| --- | ---: | ---: | ---: |
| `encoded-fu2p2q` | -15.5% to -15.3% | -0.0% to +0.0% | -1.1% to -1.1% |
| `encoded-hello` | -15.3% to -15.2% | -0.0% to +0.0% | -1.3% to -1.3% |
| `encoded-max48` | -12.9% to -12.9% | -0.0% to +0.0% | -4.9% to -4.9% |

## Work skipped

In each measured six-request block the candidate omitted 236 vocabulary projections and 75,520 scores, while retaining all 874 processed positions and 632 emitted output bytes. The control and candidate both return output token IDs to the CPU. Physical AXI polling traffic was outside the measurement scope.

## Module energy

Each arm integrated power from the first admission to the last verified finish of a six-request block. Each block produced 632 useful output bytes. The interval includes the same post-request checks and gaps on both arms. The sensor measured only the module supply, VCC_SOM.

| Pair | Full scoring / Skipped prompt scores (J per verified completion) | Full scoring / Skipped prompt scores (output tokens/J) |
| --- | ---: | ---: |
| 1 | 1.704 / 1.651 | 61.81 / 63.81 |
| 2 | 1.698 / 1.650 | 62.04 / 63.85 |
| 3 | 1.698 / 1.651 | 62.05 / 63.79 |

## Scope

These are three matched pairs in one boot. The measurements do not establish client delivery latency, whole-board energy, FPGA-only power or long-term stability. Request cycles from both arms, raw traces and the five power timestamp alignments are retained with the result. The physical run provides first-token latency. The matched RTL simulation records the isolated pre-projection prompt boundary.

The original memory layout is documented in the [resource baseline](../../implementations/kv260/resource-memory-baseline.md). The existing host input/output buffers and neural memory layout remain in use. [Control build](../autonomous-build-20261115T204747Z/run.json) and [candidate build](../prefill-skip-build-20261115T224330Z/run.json).

[Run record](run.json). Raw evidence is pinned under `.agents/runtime/hardware/inference/outputs/prefill-skip-20261115T224422Z-754f19`.
