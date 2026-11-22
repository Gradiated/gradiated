# Where attention spends its clocks

The observation-only replay used the adopted down-projection circuit. Across seven exact cases, 716 attention invocations reconciled to the original phase counters. The replay kept the generated RTL unchanged. All archived bus events, BOS scores, cache dumps and phase files matched byte for byte.

No request was refused and no response arrived late. Each cache term used one request clock, one response clock and one multiply-accumulate clock. This is scheduled work. Each occupied context position added 32 key and 32 value reads per invocation. The cache returned both a 16-bit key and a 16-bit value per request. The traversal used one of the two words, so 64 reads return 256 bytes per occupied position and supply 128 bytes of operands. This describes the simulated interface.

| Occupied length | Key traversal | Value traversal | Exponential | Probability division phase | Full attention |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 96 | 96 | 248 | 74 | 614 |
| 16 | 1,536 | 1,536 | 3,968 | 1,184 | 8,384 |
| 64 | 6,144 | 6,144 | 15,751 | 4,736 | 33,127 |
| 128 | 12,288 | 12,288 | 31,502 | 9,472 | 66,158 |
| 256 | 24,576 | 24,576 | 62,762 | 18,944 | 131,978 |

Values are cycles at five positions in the same teacher-forced sequence. The full window also includes score rounding, result rounding and output. Divider subcounts are part of the exclusive exponential and probability phases.

| Natural prompt | Occupied invocations | Full request | Attention part | Predicted saving from cache overlap | Predicted saving from exact EXP division |
| --- | ---: | ---: | ---: | ---: | ---: |
| Hello | 101 | 6,444,897 | 2,659,764 | 316,130 (4.9%) | 741,096 (11.5%) |
| Six-byte prompt | 135 | 9,801,277 | 4,739,644 | 564,840 (5.8%) | 1,323,052 (13.5%) |
| 48-byte prompt | 201 | 17,787,379 | 10,382,512 | 1,252,230 (7.0%) | 2,871,820 (16.1%) |

Cache overlap has a clear independent test even though the exponential offers a larger predicted saving. Study the two separately. Removing the divider on zero probability numerators could save only 0.07–0.23% of total cycles in these requests. All predicted savings refer to the simulated schedules. The FPGA timing and energy still need measurement. [Selected cache overlap experiment](../../experiments/kv260-attention-cache-pipeline-v1.md)

[Run record](run.json) · [Independent audit](audit-manifest.json) · [Preregistered profile](../../experiments/kv260-attention-profile-v1.md)
