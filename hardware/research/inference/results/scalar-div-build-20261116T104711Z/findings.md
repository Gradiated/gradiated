# KV260 exact scalar division offline build

The separately named circuit passed the routed 50 MHz checks. Source closure, routed reports and programming bytes were recovered and verified on the Mac.

| Resource | Scalar-mul-v1 | Scalar-div-v1 | Capacity |
| --- | ---: | ---: | ---: |
| bram_tile | 36.5 | 36.5 | 144 |
| dsp | 30 | 30 | 1248 |
| lut | 33993 | 34533 | 117120 |
| occupied_clb | 6141 | 6231 | 14640 |
| register | 12828 | 13112 | 234240 |
| uram | 0 | 0 | 64 |

Setup slack 3.722 ns. Hold slack 0.031 ns.

Vivado reported 72 advisory warnings and zero DRC errors or critical warnings.

The candidate desktop archive and all build inputs are pinned in the [run record](run.json).
