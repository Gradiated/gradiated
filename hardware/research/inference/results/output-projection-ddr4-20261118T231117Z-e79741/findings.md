# DDR4 board attempt stopped during DMA driver probe

The first physical attempt programmed the 50 MHz dual-mode fixture, applied its direct DMA overlay and verified both HP0 AFI width registers at `0x3b1`. The kernel then logged `-EIO: low DDR DMA unavailable` while probing the weight-buffer driver. The supervisor stopped at its kernel-notice gate. It issued zero fixture inference requests and collected zero timing or energy samples.

The attempted driver returned at `dma_set_mask(..., DMA_BIT_MASK(31))`, before allocation or mapping of the weights. Linux 6.8's direct DMA support check uses the system memory or DMA zone limit for masks below 32 bits. This probe result establishes a driver admission failure on this boot. The check occurred before any HP0 DDR read could be exercised. [Linux 6.8 direct DMA source](https://raw.githubusercontent.com/torvalds/linux/v6.8/kernel/dma/direct.c)

The supervisor removed the experiment driver and overlays and restored the original research firmware and weights on the same boot. All 320 original BOS logits matched the pre-attempt digest. The original FPGA manager, overlays, UIO and AFI bindings returned. Both HP0 width registers returned to `0x3b0`, with matching FPD reset and SMMU readbacks. The expected out-of-tree and unsigned-module kernel taint remained set after unload.

[Run record](run.json) · [Verified evidence manifest](audit-manifest.json) · [Routed fixture](../output-projection-ddr4-build-20261118T225153Z/findings.md)
