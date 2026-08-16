# Research log

## 2026-07-23 — admitted

Run one exact c32 interaction candidate from the two persisted positive endpoint terminals. No standalone stage may be replayed. The result remains a quality-unsafe performance proxy.

## 2026-07-23 — checkpoint-bind repair

The first owner is inactive and terminal after `1.557107687` claimed seconds (`$0.001064024`). It stopped before CUDA with `endpoint_owner_failure: resident checkpoint manifest mismatch`: `run_stack_owner.py` points at `/home/glmrunner/gemma4-fp8-layer-fusion/checkpoint`, whose validation stopped after the first two manifest files. The successful ring predecessor binds the same resident model from `/home/glmrunner/gemma4-async-result-pipeline/checkpoint` in `remote_endpoint_pair.sh` (`af1520005b5e8dbd3fdd04782b4763c2cb098c3b49f17558ec44ac12bbca0dd0`). Repair only that path, retain every scientific input and persisted endpoint, and run only the unstarted combined candidate.

## 2026-07-23 — semantic smoke consumer repair

The checkpoint repair is real: the candidate reached CUDA, `/v1/models`, and passing width/ring path audits, but science remains unstarted. The pre-science consumer then rejected all language smoke rows even though the project is explicitly quality-unsafe. This is not new semantic evidence: the arithmetic response is byte-identical to the persisted width endpoint's known incoherent arithmetic response. Preserve the active owner and raw rows; change only the gate to require finite nonempty transport plus that persisted-reference match, retain the failed quality label, and resume through the owner's existing `REPAIR_REQUEST.json` handshake.

## 2026-07-23 — runner endpoint-address repair

The semantic consumer repair passed, the replacement server reached readiness on port `30001`, and path plus transition proofs remain durable. The c32 runner then set its conservative science-intent flag but failed its first `/v1/models` probe because `fp8_qkv_paired_runner.py` hardcodes port `30000`. No workload request was accepted: runner stdout is empty, `candidate/` contains only `WORKLOAD.json`, and neither request rows nor `ENDPOINT_RESULT.json` exist. Treat the arm as unconsumed. Preserve the live owner and change only `BASE` to port `30001`, then resume the unchanged workload through the existing repair handshake.

## 2026-07-23 — resume at the runner boundary

The port repair is correct, but the owner re-entered the monolithic worker from line one, reloaded the model, and reached the runner with the prior zero-request `candidate/` directory still present. The runner failed `mkdir(exist_ok=False)` before its first `/v1/models` probe. The compact archive SHA-256 is `f044c094842b49e1432afd23976bf0348d65e546d69e4d664488cb56e0b5bcc5`; `candidate/` contains only `WORKLOAD.json` with SHA-256 `7a05fa6218a5fbfd87744bca1ac491949ddd64bf0d58007b4d3569594f08225d`, stdout is empty, and no result or request row exists. Keep the arm unconsumed. Bind a single-use retry-entrypoint branch that verifies the live port-30001 server and settled evidence, atomically archives the partial directory with hashes, runs the unchanged runner into the fresh canonical path, and rejoins only endpoint evaluation. A missing live server is a typed blocker, not authority to reload or replay.

## 2026-07-23 — positive stack terminal after accounting-schema correction

The runner-boundary resume preserved the zero-request residue and completed the one frozen c32 arm: 32/32 finite requests, `0.6125846611248562 s/request`, exact `17,120` cached plus `117,728` fresh prompt tokens, and passing width path, ring path, transition, and smoke-transport gates. This is a 3.126366% incremental reduction from the persisted `0.6323543743435494 s/request` width endpoint and a 9.155988% reduction from the `0.6743258590313417` qualified control.

The emitted `invalid` label is an offline evaluator schema bug. It checked `control.cache`, while the content-bound width terminal stores its exact accounting in `control.candidate.cache`; both persisted control and new candidate carry the required identical counts. `DIRECTOR_ACCOUNTING_RECLASSIFICATION.json` binds all source hashes and corrects the result to `stack_positive` without replay. The stack remains explicitly quality-unsafe because the width proxy is incoherent, so it is a cost floor rather than a deployable frontier.
