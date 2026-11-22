# KV260 power logger comparison

Protocol `kv260-conditioned-logger-comparison-v1`.

All six measured blocks completed with exact output checks. The original model’s BOS check passed after restoration.

Signed change with logging on, as a percentage of logging off.

| Metric | Pair 1 | Pair 2 | Pair 3 |
| --- | ---: | ---: | ---: |
| `verified_output_bytes_per_s` | -0.03% | -0.04% | -0.35% |
| `encoded-fu2p2q.median_first_ms` | -0.13% | -0.05% | -0.07% |
| `encoded-fu2p2q.median_verified_ms` | +0.11% | +0.06% | +0.34% |
| `encoded-hello.median_first_ms` | +0.03% | -0.04% | -0.22% |
| `encoded-hello.median_verified_ms` | +0.15% | +0.05% | +0.26% |
| `encoded-max48.median_first_ms` | +0.00% | -0.03% | +0.07% |
| `encoded-max48.median_verified_ms` | +0.23% | -0.01% | +0.49% |

All observed differences stayed within the ±2% screen.
These are three paired observations from one boot.

## Energy through VCC_SOM

| Pair | Reads / missed | Gross J | Gross J per completion | Gross J per output byte | Incremental J | Incremental J per completion | Incremental J per output byte |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 350 / 0 | 27.6678 | 2.3057 | 0.0219 | 1.2323 | 0.1027 | 0.0010 |
| 2 | 350 / 0 | 27.6994 | 2.3083 | 0.0219 | 1.1731 | 0.0978 | 0.0009 |
| 3 | 350 / 0 | 27.8305 | 2.3192 | 0.0220 | 1.1996 | 0.1000 | 0.0009 |

The span below varies read timestamps as preregistered and also substitutes each bracketing idle power for their mean. This is a sensitivity check only.

| Pair | Before / after idle W | Gross J span | Incremental J span |
| --- | ---: | ---: | ---: |
| 1 | 3.022 / 3.023 | 27.653–27.674 | +1.216 to +1.241 |
| 2 | 3.022 / 3.034 | 27.687–27.702 | +1.110 to +1.230 |
| 3 | 3.029 / 3.023 | 27.819–27.835 | +1.163 to +1.232 |

Incremental estimates subtract the mean of the before and after idle powers. The JSON record retains all timing-alignment scenarios and both idle powers. The measured rail excludes other board power paths and the instrument’s calibrated uncertainty is unavailable.
