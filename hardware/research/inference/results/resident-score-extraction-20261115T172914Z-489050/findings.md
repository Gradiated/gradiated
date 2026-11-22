# KV260 verification timing and score extraction

The board verified 12 diagnostic, 18 warm-up and 36 timed requests. The original weights were restored and passed their BOS check.

## Stock verification timing

The longest return-to-verified interval was **27.52 ms** for `encoded-max48`. The earlier outlier was 80.54 ms. The exact check took 16.91 ms and the compact receipt digest took 2.85 ms. The remainder was 7.76 ms.
In the 324 requests from the earlier diagnosis, the next largest interval was 35.42 ms. A delay of the previous magnitude did not recur. Its cause remains unresolved.

For the longest prompt, exact checks that overlapped garbage collection took 16.62, 16.91 ms and included 4.36, 4.64 ms of collection. The other checks took 12.29, 12.41 ms. This pattern describes the new samples and leaves the earlier outlier unexplained.

| Prompt | Return-to-verified median / maximum (ms) |
| --- | ---: |
| `encoded-fu2p2q` | 15.87 / 16.05 |
| `encoded-hello` | 12.10 / 12.40 |
| `encoded-max48` | 25.01 / 27.52 |

## Stock versus ctypes slice

| Pair | Generation change | Verified block change | Throughput stock / slice (output bytes/s) | Gross rail J/completion stock / slice | Idle-adjusted rail J/completion stock / slice |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | -5.57% | -5.23% | 144.24 / 152.21 | 2.3170 / 2.1872 | 0.1066 / 0.0907 |
| 2 | -5.48% | -5.38% | 144.18 / 152.38 | 2.3170 / 2.1867 | 0.1028 / 0.0948 |
| 3 | -5.54% | -5.30% | 144.05 / 152.11 | 2.3192 / 2.1850 | 0.1057 / 0.0936 |

The generation-time screen passed.
The paired record retains first-byte and verified times by prompt, all power alignments, and scheduler, page-fault and garbage-collection observations from the diagnostic.

| Prompt | Median of paired stock / slice first-byte times (ms) |
| --- | ---: |
| `encoded-fu2p2q` | 46.34 / 42.80 |
| `encoded-hello` | 39.02 / 36.11 |
| `encoded-max48` | 414.36 / 388.22 |

On the KV260 CPU, the conversion-only median was 361.80 µs for stock and 95.50 µs for the slice. This test used one fixed 320-score array without inference.

Multiplying the component difference by 874 extractions gives about 232.7 ms per block. The live generation loop saved 232.4–236.4 ms. The two measurements agree at this workload's scale.

All energy values refer to VCC_SOM. The coarse power observation and small paired sample limit interpretation of differences.
