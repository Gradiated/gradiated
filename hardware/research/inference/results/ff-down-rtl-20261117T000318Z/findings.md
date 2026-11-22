# Read and multiply together in the feed-forward down projection

The candidate fetches the next operand pair during the current multiply-accumulate. It retains one arithmetic lane, the exact ordered sum, and the original rounding, saturation and output handshakes. The feed-forward scalar clone and all ten other RTL source files match the adopted divider control.

The actual 128 × 32 projection used 8,256 clocks in the control and 4,192 in the candidate. Holding results added 112 clocks to each schedule. Across three geometries, 41,032 per-term operand/product/running-sum checks and 344 row outputs matched the independent oracle. All three synchronous cancellations restarted on the retained RAM with identical results.

| Prompt | Adopted divider | Down projection pipeline | Cycle reduction |
| --- | ---: | ---: | ---: |
| Hello | 6,855,361 | 6,444,897 | 5.99% |
| Six-byte prompt | 10,349,917 | 9,801,277 | 5.30% |
| 48-byte prompt | 18,604,243 | 17,787,379 | 4.39% |

All seven exact cases matched the archived control outputs, 103,360 retained scores per arm, valid cache values, caps and BOS scores. All 716 processed positions per arm had the predicted schedule. Only feed-forward wait clocks changed, from 24,962 to 20,898 per position. Physical performance and routed implementation evidence are separate.

[Run record](run.json) · [Independent audit](audit-manifest.json) · [Experiment protocol](../../experiments/kv260-ff-down-pipeline-v1.md)
