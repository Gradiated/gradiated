# Cache overlap in the exact attention replay

The candidate requests the next cache word while it multiplies and accumulates the current registered operands. It keeps one cache request outstanding. If the next read is refused, the next request holds the same address and the current multiply-accumulate finishes once. The cache layout, order of arithmetic, softmax work and number of requests stay fixed.

The existing exact replay provides the adopted control. The candidate matched all seven full-model cases, 716 processed positions and 103,360 retained scores. Its BOS scores and both cache dumps matched the adopted reference. Every request boundary changed by the preregistered amount, and the only parent phase to change was attention wait. The ready-cache schedule hides `30L` key-request clocks and `32(L−1)` value-request clocks at context length `L`.

| Prompt | Adopted complete request, clocks | Candidate complete request, clocks | Fewer clocks |
| --- | ---: | ---: | ---: |
| Hello | 6,444,897 | 6,128,767 | 4.9% |
| Six-byte prompt | 9,801,277 | 9,236,437 | 5.8% |
| 48-byte prompt | 17,787,379 | 16,535,149 | 7.0% |

The component oracle checked 8,960 ordered key products and 8,960 ordered value products, their running sums, 560 scores, exponentials and probabilities each, and 256 context outputs across eight fully traced requests. It checked eight forced refused key lookaheads and three refused value lookaheads. Two additional bench cases reset with an accepted lookahead pending and checked the restarted output. The simulation also exercised delayed requests and replies, a corrupted response tag, and output holds.

[Run record](run.json) · [Independent audit](audit-manifest.json) · [Protocol and predictions](../../experiments/kv260-attention-cache-pipeline-v1.md)
