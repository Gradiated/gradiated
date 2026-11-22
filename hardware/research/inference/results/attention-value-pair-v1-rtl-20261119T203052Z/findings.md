# Paired attention value coordinates in RTL

Both arms matched the seven frozen fixtures, covering 716 positions per arm and 2,165,152 weighted V terms per arm. All 103,360 autonomous scores, 4,480 legacy BOS scores, output bytes, stops and cache checkpoints matched. Independent scoreboards checked every cache response against accepted append values, verified weighted products and running sums in each coordinate's original position order, and checked the ordered clipped outputs. The monitor also verified that each cache response matched one pending request and its position, coordinate and pair tag.

| Request | Exp22 clocks | Paired value clocks | Fewer clocks |
| --- | ---: | ---: | ---: |
| Hello | 3,725,233 | 3,558,785 | 166,448 (4.47%) |
| Six bytes | 5,469,940 | 5,174,020 | 295,920 (5.41%) |
| 48 bytes | 9,413,020 | 8,760,172 | 652,848 (6.94%) |
| BOS only | 26,444 | 26,396 | 48 (0.18%) |
| Hello, cap 0 | 285,544 | 283,256 | 2,288 (0.80%) |
| Hello, cap 1 | 285,544 | 283,256 | 2,288 (0.80%) |
| Full 256-position context | 13,284,148 | 12,227,380 | 1,056,768 (7.96%) |

| Prompt | First useful byte, clocks | Last useful byte, clocks |
| --- | ---: | ---: |
| Hello | 285,544 → 283,256 | 3,677,539 → 3,514,339 |
| Six bytes | 339,920 → 336,800 | 5,414,954 → 5,123,370 |
| 48 bytes | 3,393,048 → 3,239,400 | 9,343,976 → 8,697,576 |

The sweep takes prefixes of the same fixed 256-position token sequence. Each row measures admission of its final token through acceptance of its 320th vocabulary score. The terminal register advances one further clock. Earlier prefix positions still run attention and skip vocabulary projection.

| Occupied depth | Scored-step clocks | Value-phase clocks | Value-phase cache transactions | Logical weighted V terms per arm |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 26,443 → 26,395 | 192 → 144 | 32 → 16 | 32 |
| 16 | 29,589 → 29,061 | 1,152 → 624 | 512 → 256 | 512 |
| 64 | 39,812 → 37,748 | 4,224 → 2,160 | 2,048 → 1,024 | 2,048 |
| 128 | 53,443 → 49,331 | 8,320 → 4,208 | 4,096 → 2,048 | 4,096 |
| 256 | 80,707 → 72,499 | 16,512 → 8,304 | 8,192 → 4,096 | 8,192 |

There were zero extra request-refusal, response-delay and held-output clocks in this ready-cache schedule. At depth D, the paired value phase saves 16 initial requests, 16D response/data clocks and 16D compute-state clocks. The two rounds and two ordered retirements retain their original schedule. Every other model phase kept its recorded clock count. Cumulative savings match 16n(n + 2).

The score path accepts the same 32D scalar cache transactions. Each activates one K read and selects one V bank by parity. During value mixing, 32D scalar transactions become 16D paired transactions. The candidate still reads one K word per transaction, including the unused key on the value path. Each paired transaction activates both V banks, so both designs read 32D V words for that phase. The old V parity counts describe addresses in one bank. The candidate records actual enables in two banks.

Directed cases at depths 1, 2, 3, 16, 17, 64, 128, 255 and 256 checked both heads and the upper paired coordinates, Q15 full-scale probability with signed V extremes, signed ties, clipping, refused requests, delayed replies and output stalls. The cache bench checked all 8,192 ordered writes, 8,192 scalar and 4,096 pair reads with held responses, uncommitted and invalid addresses, and a pending-response reset. A corrupt pair tag or address produced an error, and resetting after even output cancelled the pending odd mate. This directed evidence uses synthetic attention inputs and the frozen table.

The first directed bench omitted the new cache input in its binding and the next checker expected one fewer recovery request. The corrected bench passed with the same generated RTL. Human attention and AI usage costs were unavailable.

[Run record](run.json) · [Implementation and local restart commands](../../implementations/kv260/variants/attention-value-pair-v1/README.md) · [Protocol](../../experiments/kv260-attention-value-pair-v1.md)
