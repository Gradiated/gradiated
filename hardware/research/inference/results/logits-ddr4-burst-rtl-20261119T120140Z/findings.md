# Exact final-score DDR4 replay

The adopted Experiment 13 control and the DDR-only candidate matched all seven frozen model cases, across 716 processed positions per arm. The replay checked every emitted logit, output byte, stop reason, and both cache checkpoints. The candidate kept the original skips for prompt positions that do not need scores.

Each candidate scoring pass accepted 320 read commands and 2,560 64-bit response beats carrying 20,480 bytes. All 10,240 signed coefficients participated in their original eight-lane dot products. The modeled responder added 320 address-backpressure clocks and 3,840 response-wait clocks per scored position. With the 2,880 fixed staging clocks, that made exactly 7,040 extra clocks per scored position. The arithmetic and ordered output took their original 1,680 clocks. Every extra clock appeared in the final-score stage. The measured wait values describe the simulated handshake pattern.

| Case | Scored positions | Control clocks | Candidate clocks |
| --- | ---: | ---: | ---: |
| BOS, cap 0 | 1 | 38,081 | 45,121 |
| fu2p2q, cap 255 | 123 | 7,475,095 | 8,341,015 |
| hello, cap 0 | 1 | 416,191 | 423,231 |
| hello, cap 1 | 1 | 416,191 | 423,231 |
| hello, cap 255 | 91 | 5,142,970 | 5,783,610 |
| 48-byte prompt, cap 255 | 105 | 12,716,857 | 13,456,057 |
| Full context, cap 0 | 1 | 17,829,940 | 17,836,980 |

The independently encoded, payload-pinned matrix was checked against every actual MAC operand in all model replays. In the perturbation run, zeroing only external score row 256 changed that BOS logit from 494,385 to 0. All 32 local embedding coordinates for the same token and all other 319 logits remained exact. A separate synthetic fixture checked all 10,240 signed partial sums and 320 row outputs, with held output acceptance, positive and negative round-to-even ties, and clipping with a reduced result width.

Injected address and response timeouts, non-OKAY and wrong-ID responses, early and late RLAST, and resets with stalled or partially returned bursts exercised nine cases. Safe release waited for verified drain. Each case reconfigured the model and checked all 320 freshly fetched BOS logits. The RTL record pins the protocol used for this replay and build; the archived revision clarifies the physical DMA allocation API.

[Run record](run.json) · [Experiment protocol](../../experiments/kv260-logits-ddr4-burst-v1.md)
