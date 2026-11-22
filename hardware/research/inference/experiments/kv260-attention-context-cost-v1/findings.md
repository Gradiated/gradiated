# How one KV260 prediction grows with context

On the selected Experiment 13 circuit, a scored prediction takes **38,081 clocks at one occupied KV-cache row** and **104,585 clocks at 256 rows**. At 50 MHz those counts correspond to about 0.76 ms and 2.09 ms of FPGA time. The extra work is in attention. Each earlier token’s key and value are already saved, but the new prediction still has to decide how much to use from each row. [Experiment 13 RTL replay](../../results/attention-exp-pair-v2-rtl-20261117T230104Z/findings.md)

| Occupied KV rows | Scored prediction, clocks | Scored prediction, ms at 50 MHz | Attention wait, clocks | Probability division phase, clocks | Shorter divider forecast, clocks saved |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 38,081 | 0.76162 | 438 | 74 | 48 |
| 16 | 41,947 | 0.83894 | 4,304 | 1,184 | 768 |
| 64 | 54,474 | 1.08948 | 16,831 | 4,736 | 3,072 |
| 128 | 71,177 | 1.42354 | 33,534 | 9,472 | 6,144 |
| 256 | 104,585 | 2.09170 | 66,942 | 18,944 | 12,288 |

[Cache-depth data](cache-depth.csv) contains all 256 points from one fixed input sequence, with the components and the conditional divider forecast. These are cycle reconstructions from the archived RTL simulation. The times just convert cycles at the 50 MHz design frequency. The full-context fixture is simulation-only.

## What each row counts

The attention controller reports its actual occupied length after the current token’s key and value have been written. Depth one therefore includes the current token, and depth 256 is the final supported position. The full-context fixture feeds 256 fixed token IDs, checks the final vocabulary scores and emits no reply. It skips the vocabulary projection at positions 1 to 255, then runs it at position 256.

For an equally scored prediction at each depth, use **37,643 fixed clocks** plus that position’s reconstructed attention wait. The fixed budget includes **1,681 clocks** to launch and run one final vocabulary projection. This gives every chart point the same scoring work. To obtain the corresponding cost without final scoring, use 35,962 fixed clocks plus attention. Each chart point covers one prediction. It excludes the time to fill the earlier cache rows and to deliver output to the host.

For the actual 256-position fixture, the prefix snapshot is taken on entry to the first vocabulary projection before its launch is counted. There are 35,962 fixed clocks per position, 8,621,987 attention-wait clocks summed across the prefix, and one fewer idle clock in the prefix snapshot than in the completed-position accounting. The totals are:

- **Prefix before the scoring launch:** `256 × 35,962 + 8,621,987 − 1 = 17,828,258` clocks.
- **Completion after one scoring projection:** `256 × 35,962 + 8,621,987 + 1,681 = 17,829,940` clocks.

The 1,682-clock difference between the two snapshots includes the remaining idle clock in addition to scoring. The script checks both boundaries for all seven Experiment 13 cases against the raw phase and cache snapshots.

## Conditional shorter-divider forecast

The trace records two attention heads, with one probability division per occupied row per head. The previous profile accounts for 37 clocks per division including setup and result handling, with 32 clocks in the radix-four loop. The selected circuit retains this probability path after the earlier cache pipeline change and Experiment 13’s paired exponential change. Reducing the inner loop from 32 to eight clocks therefore predicts **48 × occupied rows** fewer clocks for a single scored prediction. At 256 rows this is **12,288 clocks, or 11.75%** of the reconstructed scored prediction. [Experiment 13 implementation](../../implementations/kv260/variants/attention-exp-pair-v2/README.md)

A whole request visits successively deeper positions. Through the end of a request that processes `m` positions, the forecast is the sum of `48 × n` for `n = 1` to `m`, or `24 × m × (m + 1)` clocks. First output uses the same sum through the complete prompt. Prompt positions that skip final scoring still run attention and contribute to these forecasts.

| Existing request | Prompt positions | Completed positions | Saved clocks to first output | Baseline completion, clocks | Saved clocks to completion | Completion reduction |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Hello | 11 | 101 | 3,168 | 5,142,970 | 247,248 | 4.81% |
| Six-byte prompt | 13 | 135 | 4,368 | 7,475,095 | 440,640 | 5.89% |
| 48-byte prompt | 97 | 201 | 228,144 | 12,716,857 | 974,448 | 7.66% |

[Request forecasts](request-forecasts.csv) also records the prefix, first useful output, last useful output and completion boundaries for all seven replay cases. An empty output field means there was no useful output in that fixture. Savings assume the proposed divider is exact, all other schedules are unchanged and the circuit meets 50 MHz. These figures forecast internal FPGA cycles. The eventual comparison measures board-side latency, output rate and module energy separately.

## Reproduce the tables

From the repository root, run:

```sh
python3 hardware/research/inference/experiments/kv260-attention-context-cost-v1/reproduce.py
```

The script uses only the Python standard library, reads archives in place and checks both CSVs byte for byte. Add `--write` to regenerate the CSVs beside the script. Use `--repo-root` when running outside the checkout.

- [Experiment 10 observation-only run](../../results/attention-profile-rtl-20261117T104256Z/run.json) pins `replay.tar.gz`. Its `replay/cases/<case>/attention-profile.txt` records the disjoint attention states before the cache and exponential changes, including probability control and radix-step counts.
- [Experiment 13 exact replay](../../results/attention-exp-pair-v2-rtl-20261117T230104Z/run.json) pins `simulation.tar.gz` and `model-results.json`. In `replay/<case>/`, `attention-pairs.txt` and `overlap-profile.txt` supply the later exponential and cache timings. The script replaces only those matching windows in the earlier breakdown, checks the count and order of probability events in `attention-events.txt`, then reconciles `phases.txt`, `cache.kv` and `model-results.json` at both request boundaries. Hashes and byte sizes are verified before the traces are used.
