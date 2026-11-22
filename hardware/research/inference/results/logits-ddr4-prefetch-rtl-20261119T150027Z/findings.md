# Double-buffered DDR logits · RTL replay

The candidate matched the serialized control against the same frozen oracle in seven cases per arm. Each arm replayed 716 model positions, with exact scores for 323 scored positions, 317 output bytes and exact cache checkpoints and stop reasons. All scored positions had the same per-position profiling totals within their arm. Positions that skipped scoring issued no DDR reads.

| Per scored position | Serialized | Prefetch |
| --- | ---: | ---: |
| Accepted 64-byte addresses | 320 | 320 |
| Accepted 64-bit response beats | 2,560 | 2,560 |
| Useful score bytes | 20,480 | 20,480 |
| Address stalls | 320 clocks | 320 clocks |
| Response waits | 3,840 clocks | 3,840 clocks |
| Reader work including launch | 7,080 clocks | 7,080 clocks |
| Exposed wait for a complete group | 7,040 clocks | 5,441 clocks |
| Reader work during MAC | 0 clocks | 1,248 clocks |
| Reader work during rounding or streaming results | 0 clocks | 351 clocks |
| Accepted AXI handshake during MAC | 0 clocks | 507 clocks |
| Accepted AXI handshake during rounding or streaming results | 0 clocks | 156 clocks |
| Projection busy | 8,720 clocks | 7,121 clocks |

The simulator allowed alternating zero and two address stalls and an independent repeating zero, one, two and three response waits. Both readers spent one launch clock per group. Each coordinate-zero capture coincided with that group's final response clock in the full-model cases. The first group in both arms incurred 176 exposed clocks. For each of the other 39 groups, the candidate covered 32 MAC clocks and nine rounding or result clocks with next-group reader work. This accounts for the full 1,599-clock difference in exposed wait and projection busy. The direct handshake counts exclude idle AXI wait clocks. The direct reader-work counts include those clocks and the per-group reader launch. The register-based inference subtracts exposed wait from accepted addresses, accepted beats and both kinds of transport waits, with launch and original capture clocks cancelling in aggregate.

The directed checks completed 20,480 signed partial sums and 640 ordered scores, including ties and clipping. They held results under backpressure until the next slot filled, confirmed the reader stopped one group ahead, exercised final-response capture when PRIME had to wait for the next group, and supplied different DDR scores to a fresh invocation. Twelve fault and cancel cases covered bad response, wrong ID, early and late RLAST, address and response timeout, and reset with stalled or partially completed traffic. Three cases targeted next-group prefetch while group zero was scoring. Each recovered by draining only the outstanding burst, then fetching a fresh complete score matrix and verifying exact BOS scores. A separate perturbation changed the external tied score row while checking that the on-chip embedding stayed intact.

The 1,599 clocks represent 31.98 µs per scored position at 50 MHz. The deterministic simulation measures the schedule under its configured interface stalls. Physical service timing, resource use and power are measured separately.

[Run record](run.json) · [Artifact identities](artifacts.json) · [Experiment protocol](../../experiments/kv260-logits-ddr4-prefetch-v1.md)
