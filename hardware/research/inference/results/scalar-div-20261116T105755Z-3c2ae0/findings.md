# KV260 exact scalar division

One physical KV260 at the same reported 50 MHz ran the frozen W16A16 model with two control paths. Both arms used the same host reader and AU02 interface. The new divider produces two quotient bits per calculation clock. It uses 32 steps and one finish clock, compared with 64 steps in the control. Both arms process the same positions, preserve the same KV cache and skip the same unused prompt scores.

The candidate matched 139,840 signed scores in separate full-score diagnostics. All compact completions, their stops and context counts matched. The one-byte and zero-byte caps passed. The original firmware and pinned weights were restored and the original 320 BOS scores matched. Full weight-memory readback was outside the test.

## Request timing

Each table entry is the median of two requests for that prompt and arm. Time starts before prompt preparation and context clear. The CPU timestamps each usable output byte. Decode rate divides the number of output bytes after the first by the time between first and last output. Completion includes stop handling and final output drain. Post-request checks are timed separately.

| Pair | Prompt | First byte, Scalar multiply / Scalar division (ms) | Decode, Scalar multiply / Scalar division (bytes/s) | Completion, Scalar multiply / Scalar division (ms) |
| --- | --- | ---: | ---: | ---: |
| 1 | `encoded-fu2p2q` | 19.22 / 14.61 | 350.09 / 460.05 | 368.64 / 280.43 |
| 1 | `encoded-hello` | 16.08 / 12.23 | 387.30 / 503.03 | 249.14 / 191.60 |
| 1 | `encoded-max48` | 200.59 / 146.06 | 252.39 / 341.74 | 613.50 / 450.96 |
| 2 | `encoded-hello` | 16.23 / 12.37 | 387.30 / 503.03 | 249.29 / 191.75 |
| 2 | `encoded-max48` | 200.60 / 146.09 | 252.39 / 341.74 | 613.51 / 450.99 |
| 2 | `encoded-fu2p2q` | 19.09 / 14.46 | 350.09 / 460.05 | 368.52 / 280.28 |
| 3 | `encoded-max48` | 200.76 / 146.25 | 252.39 / 341.74 | 613.67 / 451.14 |
| 3 | `encoded-fu2p2q` | 19.07 / 14.49 | 350.09 / 460.05 | 368.49 / 280.31 |
| 3 | `encoded-hello` | 16.08 / 12.23 | 387.30 / 503.03 | 249.14 / 191.60 |

Relative change is the candidate divided by the control, minus one. Ranges below cover the three paired medians.

| Prompt | First-byte time | Decode rate | Completion time |
| --- | ---: | ---: | ---: |
| `encoded-fu2p2q` | -24.3% to -24.0% | +31.4% to +31.4% | -23.9% to -23.9% |
| `encoded-hello` | -24.0% to -23.8% | +29.9% to +29.9% | -23.1% to -23.1% |
| `encoded-max48` | -27.2% to -27.2% | +35.4% to +35.4% | -26.5% to -26.5% |

## Work and cycle savings

Each measured six-request block processed 874 positions, skipped 236 vocabulary projections and emitted 632 output bytes in both arms. The timed host interface returned the same token IDs. Physical AXI polling traffic was outside the measurement scope.

Internal first-byte and completion cycle deltas are listed in the run record against the exact simulated deltas. The 50 MHz simulation attributes those savings to 31 cycles removed per scalar division.

The first-byte and completion cycle savings matched simulation exactly for all 18 matched comparisons.

## Module energy

Each arm integrated power from the first admission to the last verified finish of a six-request block. Each block produced 632 useful output bytes. The interval includes the same post-request checks and gaps on both arms. The sensor measured only the module supply, VCC_SOM.

| Pair | Scalar multiply / Scalar division (J per verified completion) | Scalar multiply / Scalar division (output tokens/J) |
| --- | ---: | ---: |
| 1 | 1.288 / 0.963 | 81.76 / 109.33 |
| 2 | 1.288 / 0.963 | 81.80 / 109.34 |
| 3 | 1.285 / 0.963 | 82.00 / 109.36 |

## Scope

These are three matched pairs in one boot. The measurements do not establish client delivery latency, whole-board energy, FPGA-only power or long-term stability. Request cycles from both arms, raw traces and the five power timestamp alignments are retained with the result. The physical run provides first-token latency. The matched RTL simulation records the isolated pre-projection prompt boundary.

The original memory layout is documented in the [resource baseline](../../implementations/kv260/resource-memory-baseline.md). The existing host input/output buffers and neural memory layout remain in use. [Control build](../scalar-mul-build-20261116T001040Z/run.json) and [candidate build](../scalar-div-build-20261116T104711Z/run.json).

[Run record](run.json). Raw evidence is pinned under `.agents/runtime/hardware/inference/outputs/scalar-div-20261116T105755Z-3c2ae0`.
