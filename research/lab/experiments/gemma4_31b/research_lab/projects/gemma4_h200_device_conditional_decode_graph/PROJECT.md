# Device-conditional decode graph on H200

## Question

Can one fixed four-token device-conditional CUDA graph keep the exact one-token decode body and continuation state on GPU, removing enough host scheduler and launch round trips to improve the qualified c32 endpoint without changing batching, outputs, or model kernels?

## Why this matters

The current exact-stack trace attributes `1.277660849 s` (`5.7179%`) to scheduler gaps and another `0.270515005 s` (`1.2106%`) to launches. The prior host-side `--continuous-decode-steps 4` flag regressed `1.2507%`, and the source-bound schedule-stream penalty snapshot regressed `0.0175%`. Those interventions remained host-orchestrated. This project asks a different causal question: whether the complete one-token serving body, including sampling/penalty/KV metadata updates and loop continuation, can remain in a CUDA conditional graph for a fixed bounded replay.

The physical prediction is fewer host wakeups and graph launches, not faster model kernels. Synchronization envelopes are not credited as removable. The intervention is admissible only if an exact current-source binding and a small actual runtime discriminator show device-resident continuation with exact state and a conservative whole-request bound of at least 3%.

## Immutable identity

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: SGLang v0.5.13 commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2`, pinned Linux/amd64 image digest `6113665a…`.
- Workload: exact c32, 32 requests, 4,214 prompt and 358 completion tokens each, exactly 17,120 cached and 117,728 fresh prompt tokens.
- Control: qualified endpoint at `0.6743258590313417 s/request`.
- Candidate: fixed repeat count four, device-resident continuation, unchanged one-token model body and output semantics.

`DIRECTOR_BINDING.json` and `verify_director_binding.py` bind the current trace and the two closed host-side scheduler interventions so this project cannot replay either.

## Immediate experiment

Use `$kernel-research` for mechanism-level CUDA/runtime work. First freeze the live worker, CUDA, and graph source actually used by the pinned image. Prove or falsify that Hopper's installed runtime can capture/launch a conditional or equivalent device-driven four-iteration graph containing the full current one-token body, with completion/EOS masking and per-request KV, sampling, penalty, and cache metadata remaining correct.

Prepare offline behind `gemma4_h200_e5m2_local_fa3`. After its release and a durable `$14` reservation, claim the same H200. Run one tiny actual-runtime discriminator with fixed repeat four. Require output/state equivalence to four ordinary one-token steps, mixed completion lengths, padded graph slots, and exact proof of fewer host scheduler round trips and graph launches. Do not interpret an isolated synthetic graph-loop microbenchmark as sufficient.

Promote to exactly one profiler-off c32 control/candidate pair only if source support is real, the complete-body discriminator passes, and the conservative scope-matched bound is at least 3%. Require 32/32 sane responses, exact accounting, unchanged token semantics, and candidate path events. A minimum trace after a positive endpoint may validate the predicted scheduler/launch reduction.

## Stop rules and resources

Close pre-endpoint if the installed runtime lacks a usable conditional/equivalent graph path, any full-body operation requires host intervention inside the four-token replay, output/state/padding differs, the bound is below 3%, or host-roundtrip proof is absent. Close on endpoint invalidity or regression. Do not use `--continuous-decode-steps`, replay the schedule-stream snapshot, change repeat count, sweep graph variants, alter batching/workload, or claim synchronization envelopes as savings.

- Researcher profile: `deep`.
- One retained H200; at most 100 claimed GPU-minutes and 190 wall minutes from first claim.
- Project authorization: `$14.00`.
- At most 8 GiB new artifacts/build outputs; no checkpoint duplication.
- Researchers may claim/release the registered bench but may not create, drain, resize, or destroy provider resources.
