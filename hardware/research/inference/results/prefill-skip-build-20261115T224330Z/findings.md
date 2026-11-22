# KV260 prompt-score skip offline build

The separately named circuit passed the routed 50 MHz checks. Source closure, routed reports and programming bytes were recovered and verified on the Mac.

| Resource | Autonomous-v1 | Prefill-skip-v1 | Capacity |
| --- | ---: | ---: | ---: |
| bram_tile | 36.5 | 36.5 | 144 |
| dsp | 10 | 10 | 1248 |
| lut | 33238 | 33175 | 117120 |
| occupied_clb | 5869 | 5927 | 14640 |
| register | 13698 | 13712 | 234240 |
| uram | 0 | 0 | 64 |

Setup slack 5.342 ns. Hold slack 0.013 ns.

The candidate desktop archive and all build inputs are pinned in the [run record](run.json).
