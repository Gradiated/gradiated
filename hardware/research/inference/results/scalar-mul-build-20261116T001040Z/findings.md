# KV260 scalar multiply offline build

The separately named circuit passed the routed 50 MHz checks. Source closure, routed reports and programming bytes were recovered and verified on the Mac.

| Resource | Prefill-skip-v1 | Scalar-mul-v1 | Capacity |
| --- | ---: | ---: | ---: |
| bram_tile | 36.5 | 36.5 | 144 |
| dsp | 10 | 30 | 1248 |
| lut | 33175 | 33993 | 117120 |
| occupied_clb | 5927 | 6141 | 14640 |
| register | 13712 | 12828 | 234240 |
| uram | 0 | 0 | 64 |

Setup slack 3.887 ns. Hold slack 0.012 ns.

The candidate desktop archive and all build inputs are pinned in the [run record](run.json).
