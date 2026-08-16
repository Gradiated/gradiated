# Campaign terminal state after resumed RunPod test

Decision: `STOP_OR_PIVOT`.

The prior 13:00 decision was reopened by explicit user authorization for a materially changed RunPod placement. Two separately preregistered Secure A100-SXM requests then targeted exact CUDA-13/disk-positive `US-KS-2` and `US-MD-1` pools. Both returned HTTP 500 before pod creation and added `$0`. The second safe response identified an internal RunPod deployment-response parsing failure.

Final direct inventory contains zero Pods. Provider billing remains 22 rows and `$4.944724685296023`. Campaign-additional spend remains `$0.273464527`, leaving `$99.726535473` unspent. Gate A is content-addressed and passes 71/71 campaign tests plus 21/21 GLM tests, but Gate B has no valid stock throughput/SLO point.

Do not create another best-effort RunPod Pod. `US-KS-2` and `US-MD-1` are exhausted, and historical cold H100 placement retries remain forbidden. The only named continuation requires an external state change: a documented capacity reservation or API-visible deploy queue on an 80 GB NVIDIA host with the exact image confirmed ready. Reuse the frozen stock harness and run a matched tuned control on the same machine only if stock passes.

Decision artifact: `DECISION_RESUMED_2026-07-13.json` (`456f73470caf30cc74512ceb400ba620bdfb79891fb90b4442391da0011bdf94`).

No gateway product work is authorized.
