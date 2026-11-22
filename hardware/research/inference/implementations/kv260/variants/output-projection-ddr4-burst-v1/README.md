# Attention output projection with DDR beat and row reuse

Experiment 13 is the adopted circuit baseline. This fixture extends the two-mode Experiment 14 reference fixture and preserves its BRAM projection, signed multiply order, rounding and clipping. It can acquire the next coefficient from BRAM, a scalar DDR request, a four-weight beat, or a full row. The eight-beat row path waits for every response before exposing the row. Each buffered coefficient then uses the original READ and MAC schedule. The circuit does not start the next row's transfer before that row's first coefficient is requested.

The 32 × 32 signed 16-bit matrix is unchanged from Experiment 14. Each mode uses the same physical circuit and uploader. One registered AXI address is outstanding at a time. Each row starts at a 64-byte boundary within a 4 KiB AXI window. Replacing the checked 8-byte AXI responses with DDR controller activity would require different measurements.

| Mode | AXI ARs per projection | AXI R beats per projection | Interface bytes returned | Useful bytes |
| --- | ---: | ---: | ---: | ---: |
| 0 · BRAM | 0 | 0 | 0 | 0 |
| 1 · Scalar DDR | 1,024 | 1,024 | 8,192 | 2,048 |
| 2 · Beat DDR | 256 | 256 | 2,048 | 2,048 |
| 3 · Row DDR | 32 | 256 | 2,048 | 2,048 |

The host writes the exact mode to register `0x64` while both inference and the reader are idle. Its readback bits 6:5 hold the mode, bit 0 signals any DDR mode, and bits 1–4 retain the Experiment 14 transport busy, sticky fault, safe release, and counter saturation meanings. The device-visible base at `0x60` requires 64-byte alignment and a complete allocation within the 31-bit aperture. Fixture ID at `0x8c` is `0x44445232` (`DDR2`). Counter offsets `0x68` through `0x88` retain their original meanings.

For a successful request, extra capture clocks equal two launch clocks per AR handshake, plus address stalls, response wait, and one clock for each nonfinal response beat of a row burst. Use the observed accepted beats minus accepted addresses for that last term. The arithmetic takes its original cycles after receiving the requested coefficient. Context clear resets counters and drops any buffered row. Full model reset disables the mode and clears the buffer while the AXI master preserves any asserted address through acceptance and continues draining. A wrong response ID or an early RLAST cannot prove release. The reader retains ownership until it has accepted at least the declared number of matching-ID responses and a matching-ID RLAST. A misbehaving slave can keep the transport busy after inference has stopped.

Use `materialise_projection_burst.py --output RTL` to generate the fixture, and `replay_projection_burst.py --kv260 KV260 --previous PRIOR_ARCHIVE --verilator VERILATOR_DIR --rtl RTL --output RUN` to run the pinned simulation. `PRIOR_ARCHIVE` is the [Experiment 13 replay archive](../../../../results/attention-exp-pair-v2-rtl-20261117T230104Z/run.json) providing exact adopted traces and frozen model fixtures.
