# KV260 scalar multiplication

One physical KV260 at the same reported 50 MHz ran the frozen W16A16 model with two control paths. Both arms used the same host reader and AU02 interface. The scalar multiplier consumes four bits per step and finishes in 16 calculation cycles. The control uses 64. Both arms process the same positions, preserve the same KV cache and skip the same unused prompt scores.

The candidate matched 139,840 signed scores in separate full-score diagnostics. All compact completions, their stops and context counts matched. The one-byte and zero-byte caps passed. The original firmware and pinned weights were restored and the original 320 BOS scores matched. Full weight-memory readback was outside the test.

## Request timing

Each table entry is the median of two requests for that prompt and arm. Time starts before prompt preparation and context clear. The CPU timestamps each usable output byte. Decode rate divides the number of output bytes after the first by the time between first and last output. Completion includes stop handling and final output drain. Post-request checks are timed separately.

| Pair | Prompt | First byte, Prefill-skip / Scalar multiply (ms) | Decode, Prefill-skip / Scalar multiply (bytes/s) | Completion, Prefill-skip / Scalar multiply (ms) |
| --- | --- | ---: | ---: | ---: |
| 1 | `encoded-fu2p2q` | 28.02 / 19.22 | 273.30 / 350.09 | 475.48 / 368.64 |
| 1 | `encoded-hello` | 23.49 / 16.09 | 298.48 / 387.30 | 325.78 / 249.15 |
| 1 | `encoded-max48` | 273.97 / 200.60 | 204.12 / 252.39 | 784.43 / 613.51 |
| 2 | `encoded-hello` | 23.65 / 16.20 | 298.48 / 387.30 | 325.94 / 249.25 |
| 2 | `encoded-max48` | 273.96 / 200.62 | 204.12 / 252.39 | 784.42 / 613.53 |
| 2 | `encoded-fu2p2q` | 27.86 / 19.10 | 273.30 / 350.09 | 475.32 / 368.52 |
| 3 | `encoded-max48` | 274.11 / 200.75 | 204.12 / 252.39 | 784.58 / 613.67 |
| 3 | `encoded-fu2p2q` | 27.88 / 19.07 | 273.30 / 350.09 | 475.34 / 368.49 |
| 3 | `encoded-hello` | 23.51 / 16.07 | 298.48 / 387.30 | 325.80 / 249.12 |

Relative change is the candidate divided by the control, minus one. Ranges below cover the three paired medians.

| Prompt | First-byte time | Decode rate | Completion time |
| --- | ---: | ---: | ---: |
| `encoded-fu2p2q` | -31.6% to -31.4% | +28.1% to +28.1% | -22.5% to -22.5% |
| `encoded-hello` | -31.6% to -31.5% | +29.8% to +29.8% | -23.5% to -23.5% |
| `encoded-max48` | -26.8% to -26.8% | +23.6% to +23.6% | -21.8% to -21.8% |

## Work and cycle savings

Each measured six-request block processed 874 positions, skipped 236 vocabulary projections and emitted 632 output bytes in both arms. The timed host interface returned the same token IDs. Physical AXI polling traffic was outside the measurement scope.

Internal first-byte and completion cycle deltas are listed in the run record against the exact simulated deltas. The 50 MHz simulation attributes those savings to 48 cycles removed per scalar product.

The first-byte and completion cycle savings matched simulation exactly for all 18 matched comparisons.

## Module energy

Each arm integrated power from the first admission to the last verified finish of a six-request block. Each block produced 632 useful output bytes. The interval includes the same post-request checks and gaps on both arms. The sensor measured only the module supply, VCC_SOM.

| Pair | Prefill-skip / Scalar multiply (J per verified completion) | Prefill-skip / Scalar multiply (output tokens/J) |
| --- | ---: | ---: |
| 1 | 1.657 / 1.286 | 63.57 / 81.92 |
| 2 | 1.655 / 1.289 | 63.64 / 81.72 |
| 3 | 1.655 / 1.282 | 63.66 / 82.15 |

## Scope

These are three matched pairs in one boot. The measurements do not establish client delivery latency, whole-board energy, FPGA-only power or long-term stability. Request cycles from both arms, raw traces and the five power timestamp alignments are retained with the result. The physical run provides first-token latency. The matched RTL simulation records the isolated pre-projection prompt boundary.

The original memory layout is documented in the [resource baseline](../../implementations/kv260/resource-memory-baseline.md). The existing host input/output buffers and neural memory layout remain in use. [Control build](../prefill-skip-build-20261115T224330Z/run.json) and [candidate build](../scalar-mul-build-20261116T001040Z/run.json).

[Run record](run.json). Raw evidence is pinned under `.agents/runtime/hardware/inference/outputs/scalar-mul-20261116T001133Z-268099`.
