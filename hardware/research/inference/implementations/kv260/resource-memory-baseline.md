# KV260 resource and memory baseline

This is the archived Vivado 2025.2 build used for the 50 MHz resident inference baseline on the K26 (`xck26-sfvc784-2LV-c`). The accepted report and bitstream export both open the same hash-matched routed checkpoint. Removing the 139-byte Vivado header and reversing the byte order within each 32-bit configuration word reproduces all 7,797,692 bytes of the sealed firmware. The measured run verified the installed file and the live project configuration. The evidence boundary ends at those checks. [Measured run](../../results/power-paired-20261115T155436Z-fd5f12/run.json)

| K26 resource | Full routed design | Full design at synthesis |
| --- | ---: | ---: |
| CLB LUTs | 31,792 / 117,120 (27.14%) | 33,293 (28.43%) |
| CLB registers | 11,027 / 234,240 (4.71%) | 11,042 (4.71%) |
| DSP48E2 blocks | 10 / 1,248 (0.80%) | 10 (0.80%) |
| BRAM tile equivalents | 36.5 / 144 (25.35%) | 36.5 (25.35%) |
| UltraRAM blocks | 0 / 64 (0%) | 0 (0%) |

The routed totals cover the transformer, AXI and reset/clock support. Vivado also lists one hard PS8 block, whose CPU and other hard circuitry sit outside these programmable resource counts. An exact placed split of core and support resources remains unknown. A separate accelerator-only build with matching RTL used 30,682 LUTs, 10,084 registers, 10 DSPs and 36.5 BRAM tile equivalents when routed. Those counts describe a different placement and routing. The percentages are shares of K26 resources. Silicon area would require a separate measurement or model.

The routed design uses 30 RAMB36E2 and 13 RAMB18E2 primitives. Their nominal capacity totals 168,192 bytes including parity bits. The count covers all uses and reflects each memory’s width and depth. Vivado also reports 1,094 LUTs used as distributed RAM and two as shift registers. The complete design’s synthesis log identifies BRAM for the K/V, embedding, logits and several other weight and table arrays, plus LUT RAM for small working arrays. These names come from synthesis; the routed report gives whole-design counts.

## Model and working memory

| Boundary | Bytes | What is counted |
| --- | ---: | --- |
| Unique learned weights | 53,440 | 26,720 signed 16-bit parameters, with a single tied embedding tensor |
| Unique coefficient and table data | 10,244 | RoPE cosine/sine 8,192, exponential 1,028, reciprocal square root 1,024 |
| Raw tensor data | 63,684 | Weights and unique tables. The safetensors file adds 964 bytes of header and metadata |
| Exact model upload | 117,124 | 29,281 32-bit words, with 53,440 zero padding bytes in the weight words |
| FPGA K/V allocation | 32,768 | Two arrays of 256 positions × 32 signed 16-bit values |
| FPGA working arrays | 3,968 | Logical array payloads for intermediate vectors and attention, excluding scalar/control state and gain copies |

The exact upload was reconstructed from the pinned fixed tensors. Each weight uses the low half of one loader word. RoPE packs two 16-bit coefficients per word and the other tables use whole words. The loader writes the tied weights to both the embedding and output projection memories, adding a 20,480-byte copy in the RTL, and keeps a 64-byte copy of the first Q row. Three normalisation blocks also stage 192 bytes of gains per token. The upload sends each coefficient and table once. The RTL sends the exponential table to five recipients and the reciprocal-square-root table to three. These logical copies describe the source and loader, while the Vivado totals account for synthesis and packing.

The K/V cache gains 128 valid bytes per processed token position, including the prompt. Clearing the context invalidates the rows without changing the allocation. The 72 measured requests ended at 101, 135 or 201 positions across the three prompts, holding 12,928, 17,280 or 25,728 valid bytes respectively. EOS adds no cache row. Attention reuses its working arrays across heads. Its query, score, exponential and probability arrays account for 2,624 of the 3,968 working bytes.

Each resident native session keeps a 117,125-byte ctypes upload buffer including its terminator and 120 bytes of native state. A scoring call receives 320 32-bit scores and five 32-bit result counters in separate host buffers. The CPU uploads weights once per native session and exchanges tokens and scores over the 4 KiB mapped MMIO window. The score data alone is 1,280 bytes per step, plus index/status transactions. The CPU chooses the next token. Python score lists, benchmark captures, temporary package checks and process memory have no measured peak in this baseline.

File sizes, hashes, individual resource rows and memory arithmetic are in [the baseline data](resource-memory-baseline.json). To verify the archived inputs, use the original checkout in [the storage register](../../storage.json). The current Mac copy is under `/Users/aidanmcconnell/dev/gradiated/.agents/runtime/hardware-consolidation/2026-11-14/server-runtime`. From the hardware worktree root, run:

```sh
.agents/runtime/hardware/inference/venv/bin/python3 -B \
  hardware/research/inference/tools/records.py verify-artifacts \
  hardware/research/inference/implementations/kv260/resource-memory-baseline.json \
  --root /Users/aidanmcconnell/dev/gradiated/.agents/runtime/hardware-consolidation/2026-11-14/server-runtime
```

The recorded extraction command and read-only checker are saved locally under `.agents/runtime/hardware/inference/outputs/kv260-resource-baseline-20261115/`. The SHA-256 of `extract.py` is `8557d44016cdecb2798ce0ca6cbb41950cbae2877d38070074134e14f3e66a09`. The checker compares the archived receipts, reports and binaries, checks the matching current RTL and host sources, repacks the tensor bytes, and reads the context counts from the verified performance receipts.
