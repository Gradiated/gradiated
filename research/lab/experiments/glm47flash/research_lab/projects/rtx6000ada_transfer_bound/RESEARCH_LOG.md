# Research log

No researcher result yet. Use the shared hardware inventory and new c16 denominator to nominate one real RTX 6000 Ada measurement or close the placement; do not build provider infrastructure.

## 2026-07-15 — conservative transfer bound and venue refresh

**Question.** Can RTX 6000 Ada's same-SM89 geometry retain enough of the measured L40S c16 result to beat the campaign's $0.514/M committed-cost target at a sustainable all-in rate?

**Action.** Bound the exact current-AWQ c16 transfer from the measured 535.286 tok/s L40S control. The shared inventory confirms identical SM89, 142 SMs, 568 Tensor Cores, 96 MB L2, 48 GiB ECC GDDR6, PCIe Gen4 x16, and broad CUDA/vLLM support; RTX 6000 Ada has 960 versus 864 GB/s nominal bandwidth and 300 versus 350 W TGP. I deliberately did not claim the bandwidth uplift because the c16 trace lacks a memory-counter decomposition. Applied component intervals for kernel/runtime legality (0.98–1.00), sustained clocks/cooling (0.90–1.00), runtime support (0.98–1.00), and setup/lifecycle utilization (0.95–0.99).

**Evidence.** The resulting conservative retained fraction is **0.821–0.990**, or **439.546–529.933 output tok/s**. At the RunPod listing of $0.77/h, the low-bound cost is $0.4866/M and the required fraction is 0.7774, so the listing alone passes. Reusing the campaign's conservative 10% lifecycle allowance makes the rate $0.847/h and low-bound cost **$0.5353/M**, failing the $0.514/M target; the low-bound sustainable all-in rate ceiling is **$0.8133/h**. Fresh read-only TensorDock inventory returned eight hostnodes but no RTX 6000 Ada (A40, RTX A6000, and L40S only). Vast's live API retrieval failed at DNS/HTTP 000, retained as a provider-path failure rather than an availability result. No provider was mutated and spend was $0.

**Decision.** **Close the RTX 6000 Ada placement and nominate no measurement.** Same-chip geometry makes it plausible, but the only current exact listing fails once material lifecycle costs are included; the project cannot claim a sustainable production rate. A later measurement is justified only if authority obtains an exact-capacity, sustainable all-in quote at or below $0.813/h. The decisive on-device signals would be GPU identity/clocks/temperature/power/SM utilization, memory throughput and L2 hit rate, exact VRAM residence, and request/interrupt/reload telemetry.

See [rtx6000ada_c16_transfer_bound.json](./rtx6000ada_c16_transfer_bound.json) and [source_and_rate_evidence_manifest.json](./source_and_rate_evidence_manifest.json).
