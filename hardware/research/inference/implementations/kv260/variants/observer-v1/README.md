# Observation counters, version 1

This is a separately identified measurement circuit for the frozen `chip-joke-text-20261109` W16A16 transformer. It adds counters without changing the model, arithmetic, cache layout, parallelism, clock target or legacy AXI interface. The original `../../rtl/` remains the baseline.

[Experiment protocol](../../../../experiments/kv260-observer-v1.md) defines scope, limits and acceptance. Simulation success is not physical-board qualification. Do not replace the registered baseline with this circuit merely because it builds.

`manifest.json` pins all eleven baseline RTL files and every materialised output. `rtl/` contains four overrides. `materialise.py` checks both sets of hashes before writing a new output directory. Generate the remaining seven files from the matching baseline rather than maintaining another independent copy.

```sh
python3 hardware/research/inference/implementations/kv260/variants/observer-v1/materialise.py \
  --output .agents/runtime/hardware/inference/observer-v1/rtl
```

Run the bounded simulation suite with the pinned Verilator installation and frozen recovered board package:

```sh
python3 hardware/research/inference/implementations/kv260/variants/observer-v1/test_observer.py \
  --verilator /absolute/path/to/verilator/5.052 \
  --bundle /absolute/path/to/board-packages/conditioned-6wbein7j \
  --output .agents/runtime/hardware/inference/observer-v1/tests
```

Each compilation and simulation has a 150-second process-group limit. The tests cover two real BOS requests with all 640 scores, independent phase/handshake counts, context clear and stable snapshots, synthetic AXI busy-read and reset races, saturation and overflow, and cycle-identical baseline/variant traces under the same legacy stimulus. These are simulation evidence only. The synthetic edge test deliberately deposits a near-overflow value to avoid simulating billions of cycles.

## Readout

Read the ABI identifier at `0x24`, status at `0x28`, overflow mask at `0x2c`, and 32 counters at `0x40 + 4*i`. ABI is `0x4b563031` (`KV01`). Status bit 0 is core busy, bit 1 indicates any overflow. Values saturate at 4,294,967,295. All observations reset on context clear or core reset. Counter and overflow reads are refused while busy or coincident with token, clear or reset submission. Registers are read-only.

Only one software owner may submit tokens or take snapshots. Read counters after a completed request, verify idle status and no overflow, and verify repeat reads are stable. For timed/power blocks, wait until the sampler exits and the full active and idle windows have closed. Reading between requests would add overhead inside whole-block timing and energy.

Counter 0 records busy cycles. Counters 1–19 follow these frozen phase numbers:

| Number | Phase | Number | Phase |
| --- | --- | --- | --- |
| 1 | Embedding read | 2 | Embedding load |
| 3 | First normalisation start | 4 | First normalisation wait |
| 5 | Q/K/V front end start | 6 | Q/K/V front end wait |
| 7 | Attention start | 8 | Attention wait |
| 9 | Attention output projection start | 10 | Attention output projection wait |
| 11 | Second normalisation start | 12 | Second normalisation wait |
| 13 | Feed-forward start | 14 | Feed-forward wait |
| 15 | Final normalisation start | 16 | Final normalisation wait |
| 17 | Score projection start | 18 | Score projection wait |
| 19 | Fault | | |

These phases partition busy cycles. The protocol describes counters 20–31. Additional event and subregion counters overlap the phase totals. Cache waits are not external-memory bandwidth. Feed-forward scalar cycles include control and handshake time. CPU work between tokens is outside core busy. At verified 50 MHz, one cycle is 20 ns.

Physical qualification must compare the original firmware with this variant, including timing, VCC_SOM energy, utilisation and complete output checks. Preserve the original firmware file and use a distinct observer filename and a reviewed restoration path. A counter-enabled versus counter-disabled comparison alone cannot establish the cost relative to the original implementation.

`observer_read.c` is a separate, read-only AArch64 companion. It takes the existing owned UIO mapping, uses aligned 32-bit reads with `dsb sy` barriers, and accepts only two identical idle, non-overflowed snapshots. Its caller must verify the observer firmware before any access. It does not replace the sealed inference library. Cross-compile using the existing Vivado Clang/LLD tools with warnings treated as errors. The physical run pins its resulting library separately.

## Offline implementation result

The [15 November build](../../../../results/observer-build-20261115T180508Z/findings.md) passed at the unchanged 50 MHz target. Compared with the original routed circuit, it adds 761 LUTs and 1,017 registers, with unchanged DSP and block-RAM usage. The complete build and programming file are verified on the Mac. The subsequent [physical comparison](../../../../results/observer-qualification-20261115T182057Z-11c575/findings.md) passed exact-output, counter and restoration checks. One prompt-latency comparison exceeded the descriptive ±2% timing band, so timing neutrality remains inconclusive. The original circuit and weights were restored. This measurement variant has not replaced the baseline.
