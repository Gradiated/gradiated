# Research log

## 2026-07-23 — sole frozen H200 pair and synchronization trace

Question: can a host-maintained min-new-tokens predicate remove all 358 four-byte D2H predecessors while preserving the exact retained c32 workload?

Action: verified and materialized the immutable bound inputs under this project, claimed `h200-sync-linear-e00vhh6h29fj68x91g`, identified the source-backed read at `BatchedMinNewTokensPenalizer._apply`, froze one host-counter/dense-add intervention, passed five CUDA mixed-batch mutation cases, and ran exactly one profiler-off control/candidate c32 pair followed by one candidate trace. No provider resource was created and no intervention variant was swept.

Measured evidence:

- Mutation tests passed on NVIDIA H200 for mixed active state, counter transitions, filtering/reordering, merging different progress, and all-inactive skip.
- The exact 32/32 pair passed semantic, feature-parity, token, and cache accounting. Control was `0.6864722996874946 s/request`; candidate was `0.6762324541249995 s/request`, a `1.4916618729%` paired reduction and `1.5700524677%` below the prior `0.6870190130937459` frontier.
- The candidate missed the `0.6381105231 s/request` campaign ceiling.
- The minimum trace retained 387 long synchronization calls and all 358 four-byte D2H immediate predecessors (`12.897130083 s` total long-sync time), falsifying the preregistered 358-to-0 prediction.
- In the retained trace, all 358 synchronization-specific reads immediately followed the CUB reduction associated with boolean advanced indexing. In the candidate trace, that reduction was absent and all 358 reads immediately followed `create_flashinfer_kv_indices_triton` after scan/copy/add metadata kernels. This establishes that the original read was removed but the wait shifted to a later scalar read; the exact replacement Python callsite is unresolved because the trace lacks Python stacks.

Decision: close the exact host-gate-elimination hypothesis, retain the endpoint-positive dense-add implementation as a simple gain, and do not replay or sweep. The reconciled terminal is `artifacts/host-gate-20260723t0003z/RECONCILED_TERMINAL.json`; the raw persisted pair and trace counter remain authoritative inputs.

Spend and handoff: the claim ran from `2026-07-22T23:48:53.161156Z` through release at `2026-07-23T00:31:31.763197Z`, conservatively settling `2558.602041 s` at `$2.46/hour` or `$1.74837806135`. The bench was released ready and was subsequently consumed and released by `gemma4_h200_local_attention_register_residency`.
