# KV260 scalar multiply simulation

The candidate consumes four multiplier bits at once, reducing a product from 64 to 16 calculation cycles. This is an exact wide multiply with the original overflow and interface rules. It replaces only the scalar RTL in prefill-skip-v1.

Both designs matched all 103,360 retained scores per arm across seven full-circuit cases. Both returned the same outputs and stops and had identical KV snapshots. They also passed the independent scalar oracle, including 3,567 mixed operations, output stalls, and reset at each multiply step.

| Prompt | Slots processed | Cycles to final prompt projection, control / candidate | Complete request, control / candidate |
| --- | ---: | ---: | ---: |
| `encoded-hello-cap255` | 101 | 1,140,952 / 770,296 | 16,276,524 / 12,444,108 |
| `encoded-fu2p2q-cap255` | 135 | 1,359,604 / 920,308 | 23,753,596 / 18,412,444 |
| `encoded-max48-cap255` | 201 | 13,651,292 / 9,983,324 | 39,195,274 / 30,649,834 |
| `encoded-hello-cap0` | 11 | 1,140,952 / 770,296 | 1,162,074 / 791,418 |
| `encoded-hello-cap1` | 11 | 1,140,952 / 770,296 | 1,162,074 / 791,418 |
| `bos-only-cap0` | 1 | 99,412 / 66,196 | 120,534 / 87,318 |
| `full-context-cap0` | 256 | 53,432,923 / 41,824,123 | 53,454,045 / 41,845,245 |

Across the three natural prompts, cycles to the start of the final projection fell by 27–32% and complete-request cycles fell by 22–24%. In all seven cases the end-to-end gain matched all 48 saved steps per product. No two scalar units were multiplying in the same cycle in these workloads.

These are simulated cycle counts. The routed resource cost and board timings are separate results.

[Run record](run.json)
