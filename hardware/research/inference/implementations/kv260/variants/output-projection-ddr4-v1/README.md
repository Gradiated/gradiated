# Output projection from DDR4

This comparison fixture descends from the pinned `attention-exp-pair-v2` circuit. Bank 4 retains its BRAM loader and datapath. While the inference controller and reader are idle, the host can select a separate 64-bit DDR4 path to the same signed multiplier. Each row visits its 32 coordinates in order. Each coefficient issues one aligned, nonsecure single-beat AXI read and selects the appropriate 16-bit lane. A complete 32 × 32 projection accepts 1,024 addresses and 1,024 beats carrying 8,192 interface bytes for 2,048 useful bytes.

Use `materialise_projection_ddr.py --output RTL` to generate and pin the single comparison fixture. Use `replay_projection_ddr.py --kv260 KV260 --previous PRIOR_ARCHIVE --verilator VERILATOR_DIR --rtl RTL --output RUN` to replay both modes and the directed fault and arithmetic cases. `PRIOR_ARCHIVE` is the pinned simulation archive from [Experiment 13](../../../../results/attention-exp-pair-v2-rtl-20261117T230104Z/run.json). The replay checks the frozen model image and matrix digest, compiles with two jobs and has a 25-minute overall limit.

## AXI-Lite registers

The existing registers through `0x5c` retain their meanings. All added writes require the full 32-bit strobe.

| Offset | Access | Meaning |
| --- | --- | --- |
| `0x60` | RW | Device-visible base. Write while idle with DDR disabled. Valid bases are 8-byte aligned and at most `0x7ffff800`. Zero clears the base and prevents enabling DDR. |
| `0x64` | RW | Write 0 for BRAM or 1 for DDR while idle. Read bit 0 for the selected mode, bit 1 for an occupied DDR reader, bit 2 for a sticky DDR fault, bit 3 for safe buffer release and bit 4 for counter saturation. |
| `0x68` | RO | Useful bytes accepted by the multiplier operand path. |
| `0x6c` | RO | AXI read-address handshakes. |
| `0x70` | RO | AXI return-beat handshakes. |
| `0x74` | RO | Terminal DDR read faults. |
| `0x78` | RO | Extra clocks from the ordinary BRAM capture edge up to the edge before the usable DDR weight is captured. |
| `0x7c` | RO | Address backpressure clocks before fault or cancellation. |
| `0x80` | RO | Response wait clocks before fault or cancellation. |
| `0x84` | RO | Output projection invocations started in either mode. |
| `0x88` | RO | Clocks inside the output projection in either mode. |
| `0x8c` | RO | Fixture identification `0x44445231` (`DDR1`). |

Autonomous request start and context clear zero all counters and retain mode and base. The counters saturate at `0xffffffff`. In a successful request the extra clocks equal two fixed launch and address clocks per operand plus address backpressure and response wait. The same increment appears in projection busy clocks and whole-request cycles. A 64-bit return counts as eight interface bytes. DDR controller traffic requires a separate measurement.

Non-OKAY responses, a wrong AXI ID, a missing `RLAST`, or 4,096 cumulative address and response stall clocks on one operand fault the inference. FPGA soft reset through `0x1c = 2` disables DDR, clears the configuration and cancels computation while the reader preserves any outstanding address until accepted and drains the return through `RLAST`. Release the DMA buffer only after status bit 3 reads high. It remains low if a stalled address is never accepted or the slave never returns `RLAST`. Shared AXI fabric reset is a separate system operation.

## Physical comparison

The [board supervisor](physical/lifecycle.py) uses one routed circuit for both modes. Each arm starts with the same resident model and a new upload of the same 2,048 matrix bytes. Only the source selector changes. Upload and model-loading times are recorded separately. The [request checker](physical/measurement.py) compares the BRAM cycles with Experiment 13 and compares the additional DDR4 cycles with the memory reader's wait counters. The [measurement runner](physical/bench_fixture.py) uses the same three prompts, timing boundaries and module power sensor as the preceding experiment.

The run packet records the exact bitstream, overlays, temporary driver, software and configuration hashes. Its [UART transport](physical/transport14.py) recovers the board evidence with a checksum. The supervisor releases the driver-owned memory, unloads the driver, restores the original memory-port settings and verifies the original research circuit against its 320 reference scores. Linux records the external module load for the rest of that boot.
