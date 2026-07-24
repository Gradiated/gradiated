# Research log

## 2026-07-24 — director admission

Admitted one deep, candidate-only discriminator for the unresolved
occupancy-dependent SWA/KV allocator or batch-topology transition. The
persisted complete trajectories put the first HBM staircase near request 809
with 14 running requests and only 737 SWA tokens available; corpus reset did
not move the collapse. The researcher must bind one exact source ownership
event and freeze one intervention before claiming the retained H200.

The project may run one fixed 1,036-request candidate trajectory against
persisted controls and the index-aligned state-aging token comparator. Stock,
corpus, wave, QLEN, ring, quality, c32, 10K, and tuning replays are forbidden.
The H200 remains warm and available under a verified 21:00Z watchdog.

## 2026-07-24 — measured SWA leaf-pressure negative

Question: does whole-leaf SWA locking cause the request-809 pressure
transition? The bound source moves `len(node.value)` into protected SWA state
on first lock, while a default-off hook splits new leaves to one page-aligned
1,024-token window. I froze only that hook and ran the sole candidate
trajectory.

Action: enabled `SGLANG_OPT_SWA_SPLIT_LEAF_ON_INSERT=1` in immutable packet
`d81b8271...`; replayed no control or prior arm. One pre-science controller
path defect consumed 10.1 claimed seconds but no invocation. The repaired
PID-owned controller completed and retrieved the single candidate sample.

Evidence (measured): maximum locked leaf size was 1,023 tokens. At the first
HBM step, candidate SWA usage was 17,658 versus bound control 26,828
(-9,170), but the step still began at request 809.86 with 14 running
requests. HBM grew 5,166 MiB and Torch reserved bytes grew 5.96 GB.
All 1,036 requests completed; output-token sequences, finish reasons, and
usage matched 1,036/1,036. Final client queue was 9.184 s, late queue slope
was +0.0437 s/request, and planning cost was $0.140065/M. Total project
provider exposure was $0.621307.

Interpretation: leaf over-locking is real secondary pressure but is not the
collapse cause. Reject this exact mechanism. The synchronized Torch-reserved
and HBM staircase shifts the next materially different discriminator to one
concrete CUDA-graph, target-verification workspace, or batch-topology
allocation owner. See `RESULT_ANALYSIS.json`; do not replay this sample.
