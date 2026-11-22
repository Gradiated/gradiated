# Exp16 final-score DDR4 build

The BRAM control reuses the exact routed Exp13 circuit and its firmware. Preparation checks the eleven generated control modules against the admitted Exp13 input archive. A fresh Vivado 2025.2 census opens the pinned control DCP with two threads and checks the K26 part, complete route and 20 ns clock.

Materialise the two [RTL arms](../materialise_logits_ddr.py). Run `prepare.py` with the repository root, the admitted Exp13 and Exp15 build-input archives, the generated control and candidate source directories, a fresh output folder, an attempt name, and `--dma kv260-logits-ddr4-dma-direct.dts`. The candidate compiles twelve modules and uses the exact Exp15 HP0 shell. Its direct reads use ID zero, nonsecure data, and fixed eight-beat, 64-bit incrementing bursts. Its published address range is unremapped low DDR. The RTL's validated base, forty groups and eight bursts per group keep all beats inside the allocated 20 KiB image.

Extract the prepared source archive into the manifest's `remote_root` on the established Linux host. From that directory run `KV_OUTER_BUILD_UTC=$(( $(date +%s) + 2520 )) python3 -u run-all.py`. Use the 45-minute build and remote archive budget and the separate five-minute recovery limit. Recover the archive and receipt before qualifying the package. The `verify.py` help lists its required inputs, including the exact earlier images and the frozen Exp16 RTL replay.

Measure the FPGA, full accelerator, logits and reader hierarchies in the routed checkpoints. Check the eight BRAM banks in the control, block storage in the replacement scorer, local buffer cost, and continued presence of the embedding BRAM. The accounting distinguishes whole-image changes from the named final-score hierarchy.

The candidate package has a new program overlay and a direct DMA overlay for the Exp16 driver. The AFI/UIO and restoration overlays are byte-identical to Exp15. The control keeps its original program and interface overlays and uses the same qualified PL0 clock. Confirm the live board's HP0 widths, direct nonsecure DMA path and restoration baseline before using either package.
