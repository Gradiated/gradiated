# Feed-forward comparison retry stopped at qualification

The read-only capture showed the same boot, original stock overlays, normal FPGA-manager state and untainted kernel. Compared with the previous verified stock state, two new kernel notices appeared. One reported a serial input overrun. The other reported that a USB hub port was disabled and was being re-enabled. The unchanged notice gate blocked staging before the retry was assembled. The original circuit and weights stayed in place.

The serial overrun is consistent with a problem in the first USB transfer. The log cannot identify the missing or altered bytes or establish the source of the USB warning. The tested transport amendment checks each group of 32 frames. It passed all twelve local scenarios and did not run on the board. No physical performance result was produced.

[Run record](run.json) · [First transfer stop](../ff-exp-div-20261116T220204Z-8d31b7-transfer-aborted/findings.md) · [Verified routed build](../ff-exp-div-build-20261116T213813Z/findings.md)
