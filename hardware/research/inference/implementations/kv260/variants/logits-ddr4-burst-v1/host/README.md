# KV260 logits DMA companion

The candidate uses the exact packed 20,480-byte copy of the frozen tied embedding for logits. The model loader still writes the original on-chip embedding for input lookup. The exact Experiment 13 control uses its existing UIO path with no DMA companion.

The candidate companion binds `gradiated,kv260-ddr4-logits-v1` at `0xa0000060` for 48 bytes. It checks fixture ID `0x44445233` before accessing controls. The character device is root-owned and mode 0600. The root-only UIO mapping shares its MMIO page. The supervisor owns both interfaces and serializes inference with DMA commands.

The module allocates one contiguous, zeroed block of pages with GFP_DMA32 and maps exactly 20,480 bytes via the device's streaming DMA API with DMA_TO_DEVICE. The CPU fills the buffer before mapping and the DMA API performs the cache handoff. The entire device-visible interval must lie inside the low 2 GiB aperture, with a nonzero base aligned to 64 bytes. The direct path verifies both the page base and the mapped DMA address and requires them to match, rejecting bounced addresses. The 32-bit streaming DMA mask accommodates Linux's low allocation zone. The routed hardware and driver both impose the narrower 2 GiB limit. Row alignment keeps each 64-byte burst inside an AXI 4 KiB boundary.

Before applying the direct-only overlay, verify HP0 access, the live MMU-500 bypass state, and the parent device tree's identity aperture. The control image requires no DMA overlay. The candidate starts with DMA disabled. Load and verify weights before selecting DDR mode and starting a request. The driver retains the allocation on fd close and keeps an owner reference until verified release. Select BRAM in the utility to disable DDR access on the candidate. The candidate still needs DDR enabled to run the logits stage.

To tear down, stop issuing UIO commands, then explicitly clear. Only remove the module, companion node, or fixture firmware after confirming mode zero, no transport outstanding, safe release asserted, zero hardware base and no allocation. If progress stalls, use the approved bounded soft-reset-and-drain path. Retain the mapping if drain cannot be proved. Out-of-tree and unsigned-module taint persists until reboot.

Build from this directory with the exact target kernel headers:

```sh
make -j2 W=1 -C "/lib/modules/$(uname -r)/build" M="$PWD" modules
```
