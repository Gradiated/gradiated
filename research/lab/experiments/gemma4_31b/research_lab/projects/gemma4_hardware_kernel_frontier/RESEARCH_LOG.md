# Research log

## 2026-07-17 — director delegation

Activated at the user's request to emphasize hardware and kernel changes after the stock BF16 H200 floor showed only a narrow theoretical margin to AA. Run independently of the live L40S FP8/W4 measurement and return one direct, price-normalized experiment rather than a survey.

## 2026-07-17 — terminal hardware/kernel frontier

- **Question:** Which exact hardware-plus-kernel route can plausibly beat the current market frontier without duplicating the live L40S FP8/W4 lane?
- **Action:** Joined the measured H200 BF16 linear/head floors, exact L40S FP8 attention/KV residual bound, exact Gemma geometry, the typed MI355X runtime/venue blocker, and fresh shared accelerator/committed-price inventories. No provider, checkpoint, GPU, or external mutation was used.
- **Evidence:** H100 SXM is $2.80/GPU-hour planning versus H200 $3.25, with 80 GiB HBM2e, 3.35 TB/s, broad vLLM support, and exact tensor-core-friendly 5376/21504 tiles. The matched H100 planning-base market hurdle is 1.8249 completed requests/s. MI355X remains blocked by missing immutable ROCm image and executable venue; B200 needs 3.3552 requests/s at $5.15/hour. The live L40S actual-consumer lane remains the only L40S FP8/W4 measurement and was not copied.
- **Decision:** Nominate one H100 SXM experiment: stock BF16/paged hybrid attention versus actual online-FP8 linears plus FP8 KV and one fused paged hybrid local/global attention kernel, at c8/c16/c32 and the 4214/358 plus AA 10K/358 workloads. Require a 10% matched-control component gain, measured HBM/L2/launch mechanism, and >=1.8249 complete requests/s before promotion. Full contract is in `FRONTIER.json`.
- **Next:** A later authorized project may execute the nominated shared-controller H100 run; this zero-cost project is terminal and must not create a provider or duplicate the live L40S lane.
