# Routed final token-score pipeline

The `logits-pipeline-v1` circuit placed and routed at the same 50 MHz target as `scalar-div-v1`. It has +4.725 ns setup slack and +0.029 ns hold slack. The checks found complete clock coverage, zero routing gaps and zero DRC errors or critical warnings.

| Routed resources | Control | Candidate |
| --- | ---: | ---: |
| LUTs | 34,533 | 34,547 |
| Registers | 13,112 | 13,123 |
| DSP blocks | 30 | 30 |
| Block RAM tiles | 36.5 | 36.5 |

The final projection uses one DSP, six RAMB36E2 and one RAMB18E2 primitive. Vivado inferred block RAM for its weights and LUT RAM for its 32-entry input memory. The chip-wide DSP and block RAM counts match the control.

All 318 recovered archive members matched their hashes. The generated programming image matches the routed bitstream after the Bootgen word conversion. Its overlay uses the inherited `kv260-scalar-div-program.dtbo` storage name, but the overlay bytes name and select the candidate firmware. Use the verified hash when building the physical comparison packet.

The first build attempt stopped at an inherited checksum before project generation. The completed run updates that checksum, with the same candidate RTL as the exact simulation. Physical timings and energy remain pending. [Run record](run.json) · [Exact RTL replay](../logits-pipeline-rtl-20261116T125221Z/findings.md) · [Initial aborted attempt](../logits-pipeline-build-20261116T125300Z-aborted/findings.md)
