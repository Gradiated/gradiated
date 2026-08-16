# Research log

## 2026-07-15 — one retained methodology-matched AWQ session launched

Question: can one current-AWQ L40S allocation supply the methodology-matched c1 report, public load ladder, and matched internal c16 control?

Action: extended the proven direct vLLM lifecycle with a bounded `tiktoken`/`o200k_base` methodology runner. It writes seven unique 10K-input/1.5K-output streaming c1 rows (TTFT and post-first-token speed) and continuous 180-second 1K/1K phases at c1–c64, stopping only on the preregistered two-adjacent-steps-below-5%-gain rule; the existing runner retains semantic, paired-diagnostic, and exact 8K/1K c16 control evidence. The 37 focused launcher/runner tests passed. Grouped mutable checks verified current manifest `e201ed…`, revision `ab31d120…`, a matching one-line SSH key, and zero direct instances/disks. The one authorized 3,900-second/$1.00 session then created `computeinstance-e00mw8xa9r3agk1awx`, reached SSH in 92.206 seconds, and armed the independent cleanup watchdog.

Evidence: `EXPERIMENT_SPEC.json` (SHA-256 `b83b36580e7589df744c488f371eea7bdd934aa12fd0fe476174f57b979a4e42`); live artifacts under `artifacts/aa_methodology_matched_current_awq_l40s_2026-07-15/`, including typed create diagnostic and `events.jsonl`.

Interpretation: no methodology, quality, throughput, or economic result is yet available; the allocation is in its admitted bootstrap/staging phase. The sole session must be allowed to retrieve its complete archive and perform verified cleanup. Do not launch another allocation.

## 2026-07-15 — director live-state audit

Read-only audit at `13:27:17Z` found the instance reachable but scientifically idle: no `/workspace/model-awq`, transfer, server, methodology runner, or GPU allocation existed; `nvidia-smi` reported 0 MiB and 0% utilization. Locally, only the cleanup watchdog remained. Treat the prior `live` classification as stale. The sole admissible next action is recovery on this already billed instance before the original `14:24:22Z` deadline, followed by terminal artifact retrieval and cleanup; no new allocation is authorized.

## 2026-07-15 — recovery-window falsification and cleanup request

Question: can the already created allocation still complete every mandatory arm before its original watchdog deadline without another create or deadline extension?

Action: recovered read-only access to the same host and found neither the pinned vLLM base image nor derived runtime present. Started the admitted shared bootstrap; at 13:36Z the pinned image pull was still active after more than four minutes. With the remaining fixed window, the mandatory three-minute c1–c64 phases alone require 21 minutes, while runtime build, 20.17-GB transfer, server load, seven long c1 prompts, the internal control, artifact retrieval, and cleanup remained. This no longer had credible room under the original 14:24:22Z bound. Requested deletion of only `computeinstance-e00mw8xa9r3agk1awx` and its named boot disk; provider disappearance is still pending verification.

Evidence: `recovery-poll-1336.txt` in the live artifact directory records the active pinned image pull; the remote audit showed 0 GPU MiB/utilization and no model/server/workload. No request row, methodology phase, control, quality evidence, or GPU-use telemetry exists.

Interpretation: this is a controller/lifecycle setup failure after allocation, not a runtime, AWQ, quality, or performance result. The complete session route is closed by its one-allocation rule; no second allocation or repair is admissible. Next: verify instance and disk absence and mark the project terminal.

## 2026-07-15 — cleanup verified and route closed

At `13:40:17Z`, authenticated direct instance and disk inventories were both empty and the watchdog process was absent. The allocation produced zero request rows, methodology phases, internal control, or useful GPU seconds. From creation at `13:19:22Z` to verified absence, the 1,255-second interval is a conservative derived exposure bound of $0.299151 at the measured L40S-plus-disk rate; invoice settlement is not available.

Interpretation: close this one-allocation lineage as setup-only operational failure. It supplies neither the methodology report nor the retained multi-arm graduation artifact and cannot be retried by this project.
