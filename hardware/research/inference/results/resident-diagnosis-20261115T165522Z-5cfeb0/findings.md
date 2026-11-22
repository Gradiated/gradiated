# KV260 resident timing and repeated baseline

All 252 repeated-baseline requests and 18 profiling requests passed exact checks. The board also passed the 54 warm-up requests and the original-model check after restoration.

All energy figures cover VCC_SOM, the supply to the system-on-module. Whole-board input energy and the energy used by the FPGA fabric alone would require separate measurements.

| Block | Active seconds | Output bytes/s | First / last 12-request segment (bytes/s) | Gross rail J/completion |
| --- | ---: | ---: | ---: | ---: |
| 1 | 61.86 | 143.04 | 143.48 / 142.63 | 2.335 |
| 2 | 61.97 | 142.78 | 143.09 / 142.46 | 2.336 |
| 3 | 61.92 | 142.90 | 143.32 / 142.47 | 2.336 |

## Profiling observations

Each table entry is the median of the three profiled observations for that prompt. Times are milliseconds per completion. The native interval sits inside the Python step and includes FPGA execution, CPU polling, score transfer and completion checks.

| Prompt | Native | Python step outside native | Argmax | Hash | Exact check | Verified request |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `encoded-fu2p2q` | 567.144 | 51.104 | 12.476 | 7.448 | 8.510 | 657.272 |
| `encoded-hello` | 394.788 | 38.245 | 9.270 | 5.603 | 6.331 | 462.549 |
| `encoded-max48` | 953.870 | 76.236 | 10.643 | 11.090 | 12.711 | 1083.420 |

The median native share of the generation loop ranged from 88.8–91.4% across prompts. Python time around that call was 7.3–8.6% and argmax was 1.0–2.1%. The Python difference combines allocation, conversion and call overhead. A replacement needs a controlled comparison to establish any gain.

## Long block conditions

| Block | Gross rail mJ/output byte | Idle-adjusted rail J/completion | RSS before / after (MiB) | Supervisor lifetime high-water mark (MiB) | AMS readings before → after (°C) |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 22.17 | 0.106 | 49.1 / 49.6 | 57.1 | 20: 24.6 → 24.7, 7: 26.1 → 26.0, 8: 26.2 → 25.9 |
| 2 | 22.18 | 0.102 | 50.6 / 50.6 | 57.4 | 20: 24.6 → 24.8, 7: 26.1 → 26.2, 8: 25.6 → 26.4 |
| 3 | 22.18 | 0.104 | 51.0 / 51.0 | 58.0 | 20: 25.0 → 24.8, 7: 24.4 → 25.7, 8: 26.5 → 25.3 |

The temperature entries are the three AMS channels at the block boundaries. The reported memory belongs to the supervisor process, including the verification references and receipts.

## Long block latencies

Each prompt has 84 verified requests across the three blocks.

| Prompt | First output byte, median / p95 (ms) | Completion with exact checks, median / p95 (ms) |
| --- | ---: | ---: |
| `encoded-fu2p2q` | 46.33 / 46.60 | 658.98 / 660.92 |
| `encoded-max48` | 414.24 / 415.15 | 1088.15 / 1092.10 |
| `encoded-hello` | 39.05 / 39.39 | 463.86 / 465.44 |

Largest absolute timing changes by pair with the hooks enabled were 0.99%, 0.56%, 4.30%. The descriptive threshold was 2%.
The record retains each signed pair, alignment estimates, raw sample coverage and temperature and memory boundary observations.

In pair 3, `encoded-max48` verified request time changed by -4.30% with profiling. From off to on, the generation loop went from 1040.41 to 1049.00 ms, and the return-to-verified tail went from 80.54 to 22.88 ms. One pair exceeded the 2% threshold. With one observation per prompt in each arm, the phase shares are diagnostic estimates.
