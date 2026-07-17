# Research log

Delegated 2026-07-15. No experiment has run yet.

2026-07-15 — archived-trace transfer falsifier completed

- Question: can the exact-current L40S c8 archive close or promote A40 without provider access?
- Action: added `analyze_transfer_bound.py`, binding V24R2 c8 request rows (364.871 tok/s), validated trace family mix, sampled GPU telemetry, admission economics, and input hashes. `test_transfer_bound.py` passed.
- Evidence: dense-BF16 compute scaling is 0.408681 (149.116 tok/s), below the 166.819 and 176.968 gates. A deliberately non-promotional trace-family surrogate is 0.522905 (190.793 tok/s), while HBM-only scaling is 0.805556 (293.924 tok/s). The archived trace labels its 2.50 s of decode kernel duration as summed, non-additive profiler work, so it cannot identify request-critical GPU versus host/scheduler wall time.
- Decision: `CONDITIONAL_DIRECT_A40_C8_MEASUREMENT_ONLY`; do not seek controller preparation from this result. The single decisive later signal is aggregate output tok/s from one exact stock-AWQ A40 c8 8192x1024 arm with request rows and GPU telemetry. Promote at >=176.968 tok/s; close the 5% route below 166.819 tok/s; retain conditional otherwise.
- Artifact: `A40_ARCHIVED_TRACE_TRANSFER_BOUND_2026-07-15.json` (SHA-256 `2f9fa2a1bb0b40b0089bb994518c47dfdc8f6fc92ebd29befb0d1d2fa50da7b9`).
