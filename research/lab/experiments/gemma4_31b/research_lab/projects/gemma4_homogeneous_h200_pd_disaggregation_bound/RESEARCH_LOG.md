# Research log

## 2026-07-24 — calibrated CPU bound and terminal

Question: can homogeneous H200 prefill/decode disaggregation clear the
20%-lower-cost, no-p95-regression, stable-queue, >=99%-completion gate for
the exact Gemma 4 31B workload at equal GPU count?

Action: built and ran `simulator.py`, a content-addressed CPU discrete-event
simulator with request admission, FIFO phase batching up to c32, calibrated
prefill/decode service, per-request KV transfer, queueing, retry/reload
burden, fleet headroom, and p95 completion accounting. The monolithic c32
worker is bound to the measured `20.8585050230 s / 32` endpoint. Older phase
measurements are used only as a shape split and scaled to that endpoint.

Evidence: `artifacts/scenario_surface.json` contains 1,980 rows over 8/16
H200 fleets, 50–95% offered load, all integer P:D splits, 5/25/80 ms transfer,
1.10/1.25 headroom, and speed exponents 0.65/0.78/0.90. Calibration passes at
0.0% error. 120 rows are stable with >=99% completion; 66 also have p95 no
worse than monolithic. The best such row is 8 GPUs, 2:6 P:D, 50% load,
5 ms transfer, 1.10 headroom, speed exponent 0.65: derived cost ratio
0.8595 (14.05% lower), p95 ratio 0.8641, so it still misses the required
20% cost reduction. No row passes the full promotion gate. A separate 10K
input sensitivity is retained only as methodology evidence.

Interpretation: close this topology route. The result is derived simulation
evidence, not a GPU or production claim; the best case is an optimistic edge
of the uncertainty envelope and remains below the promotion threshold.

Next move: no provider mutation or GPU claim; redirect effort to the active
DFlash project. Durable artifacts: `artifacts/TERMINAL.json`,
`artifacts/decision_summary.json`, `artifacts/content_manifest.json`.
