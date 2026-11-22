# KV260 exact scalar division simulation

The original divider processes one bit per clock for 64 steps. The candidate processes two bits per clock for 32 steps and uses one final clock to round. All 4,962 logged raw quotient and remainder pairs matched, and all seven model cases produced the same retained scores, output IDs, stops and KV bits.

| Case | Divider cycles in scalar-mul-v1 | Complete request, control / candidate | Cycles saved |
| --- | ---: | ---: | ---: |
| `encoded-hello-cap255` | 47.7% | 12,444,108 / 9,568,145 | 23.1% |
| `encoded-fu2p2q-cap255` | 49.4% | 18,412,444 / 14,002,477 | 24.0% |
| `encoded-max48-cap255` | 54.7% | 30,649,834 / 22,523,587 | 26.5% |
| `encoded-hello-cap0` | 50.1% | 791,418 / 599,435 | 24.3% |
| `encoded-hello-cap1` | 50.1% | 791,418 / 599,435 | 24.3% |
| `bos-only-cap0` | 38.3% | 87,318 / 71,105 | 18.6% |
| `full-context-cap0` | 60.1% | 41,845,245 / 29,654,123 | 29.1% |

No two dividers operated simultaneously in the sampled workloads. Feed-forward gate/up matrix data preparation overlapped some division cycles, yet all 31 fewer cycles per divide appeared in the measured complete-request and pre-projection differences.

The baseline uses the same divider for exponential interpolation and variable attention/feed-forward division. Across the natural requests the three internal divisions by 45,426 in the exponential accounted for 36–41% of baseline cycles. The generic change also accelerates the rest.

These are RTL cycle measurements. Routed timing, resource use and physical timing and energy are separate evidence.

[Run record](run.json)
