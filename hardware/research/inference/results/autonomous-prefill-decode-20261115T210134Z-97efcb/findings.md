# KV260 autonomous request comparison

One physical KV260 at the same reported 50 MHz ran the frozen W16A16 model with two control paths. The baseline CPU used the tested slice-based score copy and chose the next token. The candidate FPGA sequenced each request, chose the same greedy token and stopped itself. The accelerator still calculated all 320 scores at each processed position.

The candidate matched 139,840 signed scores in separate full-score diagnostics. All compact completions, their stops and context counts matched. The one-byte and zero-byte caps passed. The original firmware and weights were restored and the original 320 BOS scores matched.

## Request timing

Each table entry is the median of two requests for that prompt and arm. Time starts before prompt preparation and context clear. The CPU timestamps each usable output byte. Decode rate divides the number of output bytes after the first by the time between first and last output. Completion includes stop handling and final output drain. Post-request checks are timed separately.

| Pair | Prompt | First byte, CPU / FPGA (ms) | Decode, CPU / FPGA (bytes/s) | Completion, CPU / FPGA (ms) |
| --- | --- | ---: | ---: | ---: |
| 1 | `encoded-fu2p2q` | 43.37 / 33.08 | 219.40 / 273.30 | 600.48 / 480.54 |
| 1 | `encoded-hello` | 36.37 / 27.71 | 235.66 / 298.48 | 419.04 / 330.01 |
| 1 | `encoded-max48` | 390.49 / 314.52 | 172.65 / 204.12 | 993.84 / 824.98 |
| 2 | `encoded-hello` | 36.62 / 27.85 | 235.45 / 298.48 | 419.64 / 330.14 |
| 2 | `encoded-max48` | 390.84 / 314.51 | 172.44 / 204.12 | 994.90 / 824.97 |
| 2 | `encoded-fu2p2q` | 43.22 / 32.94 | 219.44 / 273.30 | 600.25 / 480.40 |
| 3 | `encoded-max48` | 391.31 / 314.68 | 172.49 / 204.12 | 995.19 / 825.14 |
| 3 | `encoded-fu2p2q` | 43.21 / 32.93 | 219.34 / 273.30 | 600.50 / 480.39 |
| 3 | `encoded-hello` | 36.46 / 27.72 | 235.39 / 298.48 | 419.57 / 330.01 |

Relative change is FPGA divided by CPU, minus one. Ranges below cover the three paired medians.

| Prompt | First-byte time | Decode rate | Completion time |
| --- | ---: | ---: | ---: |
| `encoded-fu2p2q` | -23.8% to -23.7% | +24.5% to +24.6% | -20.0% to -20.0% |
| `encoded-hello` | -24.0% to -23.8% | +26.7% to +26.8% | -21.3% to -21.2% |
| `encoded-max48` | -19.6% to -19.5% | +18.2% to +18.4% | -17.1% to -17.0% |

## Communication

Each measured block processed 874 token positions. At the control interface the CPU received 279,680 scores. On the candidate the same number of scores was consumed inside the FPGA, and the CPU received 632 byte IDs. The candidate still sends 242 prompt IDs across the interface in each block, plus control reads and writes. These are logical transfer counts. Polling traffic and physical bus bandwidth were not measured.

## Module energy

Each arm integrated power from the first admission to the last verified finish of a six-request block. Each block produced 632 useful output bytes. The interval includes the same post-request checks and gaps on both arms. The sensor measured only the module supply, VCC_SOM.

| Pair | CPU / FPGA (J per verified completion) | CPU / FPGA (output tokens/J) |
| --- | ---: | ---: |
| 1 | 2.120 / 1.705 | 49.68 / 61.79 |
| 2 | 2.117 / 1.702 | 49.75 / 61.90 |
| 3 | 2.124 / 1.702 | 49.58 / 61.88 |

Across the three blocks, average active module power was 3.15–3.16 W with CPU control and about 3.12 W with FPGA control. The matched idle windows measured 3.02–3.04 W and 3.03–3.04 W respectively. Most of the energy reduction came from finishing the blocks sooner.

## Scope

These are three matched pairs in one boot. The measurements do not establish client delivery latency, whole-board energy, FPGA-only power or long-term stability. Internal candidate cycles, raw traces and the five power timestamp alignments are retained with the result. Separate prefill timing and AXI bandwidth were unavailable.

The baseline circuit and memory are documented in the [resource baseline](../../implementations/kv260/resource-memory-baseline.md). The candidate adds 1,446 LUTs and 2,671 registers, with the same DSP and block RAM counts. It adds two 256 × 9-bit buffers, or 576 logical bytes. Host peak memory was unmeasured and temperature was unavailable at the gates. [Candidate build](../autonomous-build-20261115T204747Z/run.json)

Restoration verification covered the original firmware, pinned weights and all 320 original BOS scores. Full weight-memory readback was outside the test.

[Run record](run.json) · [Independent audit](audit-manifest.json). Raw evidence is pinned under `.agents/runtime/hardware/inference/outputs/autonomous-prefill-decode-20261115T210134Z-97efcb`.
