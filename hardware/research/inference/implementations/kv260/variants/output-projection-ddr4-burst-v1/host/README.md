# KV260 DDR4 matrix ownership

The driver binds the experiment's `gradiated,kv260-ddr4-burst-v1` platform node at `0xa0000060`. Its MMIO window is 48 bytes and must expose fixture ID `0x44445232`. The root-owned character device `/dev/kv260-ddr4-weights` takes a single 2,048-byte matrix and selects the source. The regular runtime uses the existing UIO mapping. Keep the UIO node root-owned and mode 0600, keep MMIO writes to the established inference ABI, and serialize inference and control on the board. The UIO mapping is page-granular and privileged direct MMIO can reach the DDR registers.

The driver allocates one private zeroed page and copies the packed weights before mapping exactly the 2,048-byte payload for `DMA_TO_DEVICE`. The platform DMA API performs the cache handoff and returns the address programmed through MMIO. The address must be nonzero, 64-byte aligned, and the final byte must be below `0x80000000`. The CPU never modifies this page during its device ownership. The mapped range covers the complete final aligned beat. The RTL master can issue reads only, with one outstanding request. In row mode the request returns eight 64-bit beats. The row-aligned DMA window prevents a burst from crossing an AXI 4 KiB boundary.

Qualify the chosen route before inserting the module. For direct HP0, establish hardware stream bypass, inspect the live device tree through all DMA ancestors, and verify the routed DDR aperture has an identity mapping. The direct overlay declares `gradiated,verified-direct-dma` as an assertion of that review. The module additionally requires the live MMU-500 node to be disabled, no device IOMMU attachment or `iommus` property, and the returned DMA handle to equal the owned page's physical base. A bounce address fails admission. On the tested ARM64 kernel, direct DMA rejects masks narrower than the low allocation zone, so the fixture negotiates a 32-bit streaming DMA mask. The driver checks the owned page before mapping and checks the returned device address before programming the base. Both checks enforce the narrower 2 GiB routed window, including the last byte. The KV260 device tree places RAM below 4 GiB in this low bank and the other bank above 32 GiB. Allocation uses GFP_DMA32. If the page or returned mapping does not meet the aperture and identity checks, setup fails. For a translated route, use a single `iommus` specifier for enabled MMU-500 stream `0xe80` and omit the direct assertion. Verify the routed AXI read ID is zero and no other active device owns or masks that stream. The module requires a DMA domain and a group containing only its own device. Record live PS clock, reset, isolation, AFI, and SMMU state used for the board admission.

Build against the exact on-target headers. The native Linux command is:

```sh
make -j2 W=1 -C "/lib/modules/$(uname -r)/build" M="$PWD" modules
```

After the image and AFI/UIO overlays are installed and verified, install the DMA device overlay and insert the module for this session. Capture the module hash, driver log and initial status. Use the extractor output as the matrix input:

```sh
python3 weights.py status
python3 weights.py load /path/to/output-projection.bin
python3 weights.py bram
python3 weights.py scalar
python3 weights.py beat
python3 weights.py row
python3 weights.py clear
```

The utility verifies the frozen matrix SHA-256 before upload. Keep allocation and mode changes outside timed windows. The upload leaves BRAM selected. The driver checks model and transport idle before issuing control writes. The board supervisor must serialize UIO inference starts and DDR commands, including cleanup. Before enabling DDR, check that the loaded DMA base equals the hardware base and the reported length is 2,048. Read counters after completion and before the next context clear or autonomous start. Both operations reset the counters and preserve the selected mode and base. A full model reset disables the mode, clears the hardware base and requests transport drain. Check release before calling `clear`, then reload and select if continuing.

Closing the control file leaves the allocation and module reference in place. Before unloading, resetting the fabric or removing any fixture overlay, stop workloads, run `clear` and record status with safe release asserted, transport idle, BRAM selected, zero base and zero mapped bytes. If the disable command is rejected while busy, wait for completion with the watchdog and retry. If a fault prevents a trustworthy drain, keep the allocation pinned and stop the experiment. A forced overlay removal while armed can detach translation and leaves the buffer pinned until reboot. Avoid forced module removal. Kernel taint from a temporary out-of-tree module lasts until reboot even after a successful unload.
