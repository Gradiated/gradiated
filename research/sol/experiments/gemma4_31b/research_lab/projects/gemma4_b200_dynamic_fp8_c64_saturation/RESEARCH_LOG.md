# Research log

## 2026-07-28 — Runtime-FP8 saturation terminal

Question: can one higher-concurrency arm improve the measured B200 runtime-FP8
endpoint enough to reach the campaign target? Action: measured one c64 arm,
then one hash-bound c96 arm against the retained healthy server. Evidence:
c64 completed 64/64 at 0.5842848010624948 s/request; c96 completed 96/96 at
0.6164568277083428 s/request, 5.51% worse than c64 and 23.26% above the
0.500119281574996 target. Interpretation: this runtime's useful saturation
peaks before c96 for the fixed workload. Next: preserve c64 as the stackable
result and pursue a distinct source-level hot-path mechanism; do not replay
these arms. Artifacts: `artifacts/b200-fp8-c64-20260728t1546z-repair2/FINAL_TERMINAL.json`,
`artifacts/b200-fp8-c96-20260728t1556z/FINAL_TERMINAL.json`.
