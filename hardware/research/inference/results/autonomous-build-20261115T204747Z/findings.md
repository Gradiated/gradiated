# KV260 autonomous controller build

The autonomous controller passed exact simulation and the routed 50 MHz build. This record is offline evidence. It does not establish physical correctness, latency or energy improvements.

Only the AXI/controller wrapper changes. The ten neural modules and frozen model are unchanged. All 320 scores are still computed at every processed position, including intermediate prompt positions.

| Resource | Original | Autonomous | Difference | Device used |
| --- | ---: | ---: | ---: | ---: |
| lut | 31792 | 33238 | +1446 | 28.38% |
| register | 11027 | 13698 | +2671 | 5.85% |
| dsp | 10 | 10 | +0 | 0.8% |
| bram_tile | 36.5 | 36.5 | +0 | 25.35% |
| occupied_clb | 5386 | 5869 | +483 | 40.09% |
| uram | 0 | 0 | +0 | 0% |

Setup slack is 5.284 ns and hold slack is 0.007 ns at 50 MHz. Routing is complete, with no uncovered internal timing endpoints, black boxes, latches or DRC errors/critical warnings. The 32 existing DSP pipeline advisories remain, with no waivers.

Simulation matched 146,880 autonomous scores, 3,200 legacy BOS scores and the three complete frozen outputs. It also covered zero/one-output limits and synthetic tie, signed-score, final-index, reset, fault, context and backpressure cases. Recorded physical full-score traces supplied score references, and frozen integer software references supplied completion expectations.

The two 256 × 9-bit prompt/output buffers add 576 logical bytes. This is not physical silicon area or host-memory measurement. Resource differences include synthesis and placement effects.

All unique server artifacts were recovered and checksum-verified on the Mac before physical dispatch. Shared backup remains pending. Build phase wall times are in the run record. Human attention and AI cost were not available.

[Run record](run.json) · [Frozen comparison protocol](../../experiments/kv260-autonomous-v1.md)
