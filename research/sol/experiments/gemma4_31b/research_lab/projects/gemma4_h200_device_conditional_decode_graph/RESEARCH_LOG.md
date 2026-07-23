# Research log

## 2026-07-23 — director admission

- Measured: the current exact-stack trace assigns `1.277660849 s` (`5.7179%`) to scheduler gaps and `0.270515005 s` (`1.2106%`) to launches.
- Measured: host `continuous_decode_steps_4` regressed `1.2507%`; the source-bound schedule-stream penalty snapshot regressed `0.0175%`.
- Hypothesis: a fixed four-token device-conditional graph for the complete serving body removes host round trips that neither closed host-side intervention removed.
- Constraint: synchronization envelopes receive no credit; the device path must preserve complete output/KV/sampling/penalty/cache state and prove a conservative bound of at least 3% before endpoint execution.
- Decision: prepare behind the direct E5M2 FA3 lane, then run one actual full-body discriminator and at most one c32 pair.

## 2026-07-23 — fixed-repeat-four full-body discriminator

- Bound evidence: `DIRECTOR_BINDING.json` verified, and `OFFLINE_SOURCE_BINDING.json` froze the exact pinned SGLang graph, worker, scheduler, sampling, penalty, and result-processing sources plus the materialized current-stack inputs before the H200 claim.
- Measured support: on the retained H200 with Torch `2.11.0+cu130`, a native CUDA conditional `WHILE` node executed exactly four iterations (`counter=4`), and Torch exposed raw graph/exec handles. The primitive is available; CUDA API support is not the blocker.
- Source-falsified composition: the pinned `CudaGraphRunner` captures `model.forward` only. Sampling occurs after forward; result tokens cross to a host list; Python request output/EOS state is mutated on host; and the next decode allocates KV state and prepares the batch outside the graph.
- Measured actual path: one mixed completion-length `1,2,3,4` serving discriminator passed all requested/actual token and finish-reason checks. Its 45 in-window audit events included four graph replays, six host sample calls, six scheduler result-processing calls, four decode-result-processing calls, four host `prepare_for_decode` calls, and five running-batch updates. Raw graph batch sizes were `1,2,3,4`, captured sizes `1,2,4`, proving the padded path was exercised too.
- Repair accounting: two completed workloads had no worker audit events because process-local installation stopped on exact already-patched current-stack bytes; the first repair then used a replacement-fragment hash instead of the complete patched-source hash. Both were mechanically candidate-absent integration attempts. The unchanged workload was repeated only after exact source-derived guards admitted worker audit installation, under the same retained claim.
- Decision: `full_body_host_intervention_required`. Full-body state equivalence, fewer host round trips, and fewer launches were not established; the preregistered support/state gate failed. Close pre-endpoint and do not run the c32 pair. Neither the host continuous-decode flag nor scheduler-overlap replay was used.
- Spend/release: cumulative assigned provider exposure was `1547.739106 s` at `$2.46/h`, or `$1.057621725`, below the `$14` reservation. The complete compact terminal was verified at SHA-256 `d85376684547ed5ea1dd4ebb25b86f38905f665ce3eb357660e078f7ff49aa58`; the healthy warm bench was released `ready`.
