# Research log

## 2026-07-23 — director admission

Admitted one runtime-native n-gram speculative falsifier after the Frozen-KV MTP target-verify floor exceeded the full economic ceiling. No GPU has been claimed and no speculative parameters have been selected; source binding and reservation durability come first.

## 2026-07-23 — source-bound NGRAM staging boundary

Question: can one native, assistant-free NGRAM contract be measured on the retained exact c32 stack?

Action: bound `--speculative-algorithm NGRAM` to v0.5.13 defaults (`12` draft tokens, BFS breadth `1..10`, trie depth `18`, capacity `10,000,000`, no external corpus) in `NGRAM_CONTRACT.json`. The source explicitly disables overlap scheduling and mixed chunking for this route; no proposal setting was tuned. Materialized the exact 62.58-GB checkpoint and current-stack input bytes under this project, then claimed `h200-sync-linear-e00vhh6h29fj68x91g` from 07:36:25Z to 07:38:37Z after the $8 reservation check.

Evidence: remote identity and disk output at `artifacts/ngram-diagnostic-20260723t0736z/remote-identity.*` record `No space left on device` while copying the project-local snapshot to `/home/glmrunner/gemma4-h200-ngram-speculative-endpoint/checkpoint`. The partial target was removed and the bench was released to maintenance. No server container, CUDA invocation, assistant model, candidate path, output, or c32 arm began. Conservative claim exposure is `$0.091` (`132.23 s × $2.46/h`); no director-assigned shared-idle exposure was added.

Interpretation: this is a typed storage/staging boundary, not a result about native NGRAM acceptance or latency. The diagnostic and conditional pair remain unconsumed. A compatible bench needs at least one additional project-local 62.58-GB checkpoint copy, or an explicit director-authorized immutable snapshot mechanism.

## 2026-07-23 — director authorizes shared immutable checkpoint reuse

The director classifies the failed duplicate copy as an operational boundary and authorizes `DIRECTOR_SHARED_CHECKPOINT_DISPOSITION.json`: validate all resident files against the bound full manifest once, then mount or link the exact lab-owned checkpoint read-only while keeping project-specific mutable state separate. The frozen diagnostic remains unconsumed. The bench is returned ready under a replacement watchdog through `12:30Z`.

## 2026-07-23 — shared checkpoint passes; stale MTP owner blocks NGRAM before workload

Action: consumed the director disposition, claimed the H200, normalized only the manifest's coordinator-relative paths, and validated all eight resident checkpoint bytes successfully. The frozen NGRAM container bind-mounted `/home/glmrunner/gemma4-h200-flashinfer-metadata-scalar-elimination/checkpoint` read-only; it neither copied nor mutated weights. NGRAM's source defaults were observed (`12` draft tokens, breadth `10`, overlap and mixed chunking disabled).

Evidence: `artifacts/ngram-diagnostic-20260723t0804z/retrieved-repair2/CHECKPOINT_VALIDATION_REPAIR2.txt` is the complete successful full-manifest validation. During model loading, `nvidia-smi` found PID 150609 / Docker container `mtp-depth-candidate` consuming 123330 MiB. The NGRAM scheduler consequently OOM'd before the diagnostic requests were submitted; terminal and logs are retained in `artifacts/ngram-diagnostic-20260723t0804z/WORKER_TERMINAL.remote.json`, `server-start.remote.log`, and `live-gpu-owner.txt`.

Interpretation: the admitted NGRAM workload and conditional c32 pair remain unconsumed. This project cannot stop the other project's retained healthy assistant-model server. Released the bench to maintenance for director cross-project disposition. Cumulative conservative project exposure is `$0.315`: prior `$0.091` plus `$0.224` for the 08:04:28Z–08:09:55Z claimed repair session.

## 2026-07-23 — director removes terminal MTP server

The director verified that `mtp-depth-candidate` belonged to the terminal MTP project, had no GPU-pool claim or queued compatible consumer, and alone held 123,320 MiB. It was stopped and removed without touching the read-only checkpoint. Immediate verification found the container absent, zero GPU compute processes, zero MiB used, and zero utilization. `DIRECTOR_STALE_MTP_CLEANUP.json` records the disposition. Preserve the passing eight-file checkpoint validation and resume only the unconsumed frozen NGRAM startup/diagnostic after reservation.

## 2026-07-23 — NGRAM clears the exact c32 ceiling

The resumed diagnostic completed 32/32 finite nonempty outputs with exact `117728` fresh and `17120` cached prompt-token accounting. It measured `0.5862922219 s/request`, speculative acceptance `0.8765568076`, and mean acceptance length `10.6421248835`, clearing the conditional-pair gate.

One profiler-off c32 control/candidate pair then measured `0.7022385985` versus `0.5967508053 s/request`: a measured `15.02164555%` reduction. Both arms passed the same exact accounting and output gates; the candidate is below the `0.6381105231` ceiling. Candidate metrics retain the native NGRAM default 12-draft-token path and no assistant model. See `artifacts/ngram-diagnostic-20260723t0815z/PAIRED_TERMINAL.json` and `pair/`.

Interpretation: retain native NGRAM as an incremental stack candidate. Conservative cumulative exposure is `$0.730` (prior `$0.315` plus approximately `$0.415` for the 08:15:07Z–08:25Z measured session); no additional NGRAM setting or arm is authorized.
