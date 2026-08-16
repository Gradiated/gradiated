# Research log

## 2026-07-15 — Delegated

- Objective: obtain model-shape-specific L40S cache/occupancy evidence, not build a profiling framework.
- First falsifier: verify Nsight Compute counter access on a tiny target kernel before checkpoint transfer.
- If permitted, use the same bounded allocation for a 64-versus-16-expert exact-shape component profile and retain raw counter artifacts.

## 2026-07-15 — Target L40S counter probe: close Nebius route

Question/action: can this Nebius L40S expose cache and occupancy counters before any checkpoint transfer? Ran a bounded CUDA `saxpy` control under Nsight Compute 2025.2.1.0 on an L40S/AD102 (driver 580.159.04). The unprofiled control completed (`cudaDeviceSynchronize=no error`). Two distinct counter routes then failed: `ncu --query-metrics` reported a counter-measurement-library `Unknown Error`, and `ncu --set full` failed with driver `resource was unavailable`; no `.ncu-rep` was emitted. The first allocation hit a Docker-package conflict before GPU work; a corrected second allocation produced the retained diagnostic, cost `$0.07792`, and verified zero named instances/disks.

Interpretation/next move: this is a measured target-venue counter limitation, not evidence about L2/HBM traffic, occupancy, 64-way routing, or the 16-expert proposal. Do not retry this Nebius route. The next cheap decisive measurement is the exact 64-versus-16-expert synthetic grouped-GEMM proxy on a venue with confirmed exclusive Nsight Compute access, retaining L2/DRAM traffic, achieved occupancy, and group-M distribution. Evidence: `artifacts/MEASURED_NCU_COUNTER_LIMITATION_20260715.json`; raw archive SHA-256 `d38e88468f2f365394c305117945df45f997311e316b57e32990721e973d1e4a`.

## 2026-07-16 — Director terminal closure

Close the venue-search continuation. The later exact `expert_count_geometry` screen established that 16/top-4 improves group-M and L2 fit but preserves routed FLOPs without conservative endpoint transfer, while 16/top-2 has only a `7.775%` ideal ceiling below its `9.955%` gate. Without an executable merged/retrained 16-expert checkpoint, another counter venue or synthetic proxy cannot change the portfolio decision.
