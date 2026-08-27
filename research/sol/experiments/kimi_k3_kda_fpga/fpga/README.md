# KV260 KDA recurrence prototype

This project is ready for the first KV260 build and measurement.

It implements Equation 1 from the Kimi Linear technical report. It uses the recurrent decode form:

`S = (I - beta*k*kT) * Diag(alpha) * S + beta*k*vT`

`o = ST*q`

The core keeps the 128×128 state in banked FPGA block RAM. It processes one head and one token at a time. It does not yet include the Q/K/V projection GEMVs, the 2-tap gate convolution, normalization, residual addition, or model-level scheduling.

## Implemented design

- Signed 8-bit Q1.6 vectors for `q`, `k`, and `v`.
- Unsigned 8-bit Q0.8 values for `alpha` and `beta`.
- Signed 24-bit persistent state with 18 fractional bits.
- Saturating state and output arithmetic.
- Registered multiply stages.
- One block-RAM bank per processing lane.
- AXI4-Lite control and data windows at physical address `0xA0000000`.
- A C test program that recomputes every result with an independent oracle.

The default design has 16 lanes. It takes exactly 7,168 clock cycles for one 128×128 recurrent head. At 100 MHz, this is 71.68 microseconds. This value excludes input loading through AXI and all missing KDA stages.

The 32-lane candidate takes 3,584 cycles. Open-source synthesis predicts that it uses 256 DSP slices, 16 equivalent 36 Kb block RAMs, and about 25,000 LUT primitives. Use the 16-lane design for the first board smoke test. Build the 32-lane design after the 16-lane design closes timing.

## Local checks

Install the local tools:

```sh
brew install verilator icarus-verilog yosys
```

Run all checks from this directory:

```sh
make check
make lane-sweep
```

These checks run the Python unit tests, native RTL simulation, AXI simulation, Verilator lint, generic synthesis, and strict C compilation.

## Build the KV260 bitstream

AMD Vivado does not run on this Apple Silicon Mac. Run this stage on a supported x86-64 Linux or Windows machine with Vivado ML Standard and the KV260 board files installed.

On Linux:

```sh
source /tools/Xilinx/Vivado/2025.1/settings64.sh
cd research/sol/experiments/kimi_k3_kda_fpga/fpga
make vivado-kv260-l16
make vivado-kv260-l32
```

The build selects the newest installed board part whose name contains `kv260`. Set `KDA_BOARD_PART` if automatic selection fails.

The outputs are stored in:

```text
results/kv260/d128_l16/
results/kv260/d128_l32/
```

Each directory contains a bitstream, an XSA file, utilization reports, timing reports, and a power report. Do not accept a design if the post-route timing summary reports negative worst slack.

## Prepare the board

1. Boot the KV260 with the current AMD Ubuntu image.
2. Connect Ethernet and the micro-USB JTAG/UART cable.
3. Confirm that you can use SSH.
4. Keep the fan connected.
5. Record the board IP address.

Program the 16-lane bitstream from the Vivado host:

```sh
vivado -mode batch -source vivado/program_kv260.tcl \
  -tclargs results/kv260/d128_l16/kda_kv260.bit
```

Copy this `fpga` directory to the board. Then run:

```sh
cd fpga
./scripts/run_on_board.sh
```

The test must print JSON with `"mismatches":0`. It records the hardware cycle count and host-observed wall time for eight recurrent tokens. Copy the JSON result back into `results/kv260/`.

## Register map

| Offset | Access | Function |
|---:|:---:|---|
| `0x0000` | R | ID. Must return `0x4b444131` (`KDA1`). |
| `0x0004` | W | Control. Bit 0 starts. Bit 1 clears state. |
| `0x0008` | R | Status. Bit 0 is busy. Bit 1 is done. |
| `0x000c` | R | Core cycles for the last operation. |
| `0x0010` | R | Head dimension. |
| `0x0014` | R | Lane count. |
| `0x0018` | W | Beta gate. |
| `0x1000` | W | Q vector. One 32-bit word per 8-bit value. |
| `0x1400` | W | K vector. One 32-bit word per 8-bit value. |
| `0x1800` | W | V vector. One 32-bit word per 8-bit value. |
| `0x1c00` | W | Alpha vector. One 32-bit word per 8-bit value. |
| `0x2000` | R | Signed 32-bit output vector. |

## Interpretation limits

This run can establish functional correctness, cycle count, timing closure, FPGA resources, and a first power estimate for the recurrent head. It cannot establish full Kimi K3 token throughput. It also cannot support a direct B300 or Vera Rubin comparison. The next hardware control is a DDR-streamed state implementation with the same arithmetic and clock.

## Primary references

- [Kimi Linear technical report](https://yzhang.site/assets/pubs/techreport/2025/kda.pdf)
- [AMD K26 programmable-logic resources](https://docs.amd.com/r/en-US/ds987-k26-som/Programmable-Logic)
- [AMD Kria custom hardware flow](https://xilinx.github.io/kria-apps-docs/creating_applications/2022.1/build/html/docs/custom_cc_flow_example.html)
