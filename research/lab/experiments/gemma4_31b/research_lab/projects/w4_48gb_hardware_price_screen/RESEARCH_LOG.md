# Research log

## 2026-07-17 — director delegation

Activated as independent `$0` evidence while the L40S W4 owner runs. Compare A40 and RTX 6000 Ada with L40S using exact W4 capacity/shapes, shared chip facts, fresh L40S planning rates, and price/throughput break-even thresholds. Return at most one conditional matched-GPU nominee; no throughput transfer or production claim. Budgets are 45 wall minutes, 1.5 CPU-hours, 1 GiB storage, 64 MiB bounded probes, and `$0`.

## 2026-07-17 — terminal conditional nominee

Question: can either 48-GiB alternative plausibly beat L40S W4 economics without transferring L40S throughput? Action: read the fresh shared $1.10/h L40S planning rate and shared accelerator facts; inspected the pinned AutoAWQ source snapshot (`get_min_capability=75`, with CUDA Marlin still contingent on runtime/layer support); and bounded public vendor-listed on-demand rates from Ultralytics ($0.44/h A40, $0.77/h RTX 6000 Ada, $0.86/h L40S). The reproducible calculation is `calculate_screen.py` and the full labeled evidence is `HARDWARE_SCREEN.json` (SHA-256 `6d8695147d3c72995e5e0089288e5191e66e727192207f667f2b9adfbf846a20`).

Interpretation: RTX 6000 Ada is the one conditional nominee. At $0.77/h it requires 0.778x matched L40S whole-workload throughput for 10% all-in improvement, while its same SM89/142-SM/96-MB-L2 geometry and 960 GB/s bandwidth make that plausible but unmeasured. The analytical 10%-better rate ceilings are $0.935/h under an explicit 85% efficiency discount and $1.10/h under a bandwidth-proportional prior. A40 is not nominated despite its $0.44/h rate (0.444x required ratio) because its SM86/84-SM/6-MB-L2/696-GB/s configuration makes the W4 stream's cache, grid, and occupancy behavior too uncertain for the sole follow-up. No CUDA, provider mutation, live-owner polling, or throughput claim occurred.

Next move: only after the separate L40S W4 mechanism emits a passing typed terminal, run a fresh matched CUDA six-shape c16/c32 whole-workload measurement on RTX 6000 Ada and obtain a current written 12–24 month committed quote. Otherwise the nominee expires without a production claim.
