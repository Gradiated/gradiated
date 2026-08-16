# Research log

## 2026-07-17 — director delegation

Activated as the exclusive paid lane after the corrected generic CUDA project reached a clean terminal but failed source-shape reconciliation. This project must exercise the pinned vLLM consumers at `16384`/`20480` QKV, `16384` global output, and `43008` merged gate/up dimensions plus the actual per-token-head cache writer. It may not repeat direct `torch._scaled_mm`, download a checkpoint, or claim endpoint quality/throughput. Because bootstrap is expected to dominate scored time, it also preregisters one same-image conditional arm from the closed vocabulary project: actual vLLM BF16 `ParallelLMHead` at M=1/2/4/8, triggered only by a primary pass that has not already falsified both economic envelopes. Budgets are 50 wall minutes, 20 provider minutes, 0.34 L40S-hours, 2 local CPU-hours, 100 GiB provider disk, 4 GiB artifacts, and `$0.50`.

## 2026-07-17 — identity pass; shared-controller lifecycle blocker before create

Question: can the admitted actual-consumer FP8 experiment use the named shared controller while preserving the required same-owner conditional BF16 `ParallelLMHead` arm?

Action: exact-matched all five asserted input hashes and the model/image/revision/TP=1 source-derived dimensions. Audited the named `mla_microbench_control.py` once, including its custom remote/benchmark interfaces and cleanup control flow.

Evidence: `artifacts/preflight-20260717T045840Z.json` records an identity pass. The controller accepts custom scripts, but it is a foreground single-arm runner: it has no systemd service-owner proof, calls no `VerifiedRetainedOwner`, only starts a teardown watchdog, and unconditionally deletes the instance in `finally` after one `allocation-result.json`. It therefore cannot persist independently typed FP8 stages or consume their trigger to conditionally execute the actual BF16 head arm. No instance, disk, remote command, useful GPU time, or spend occurred.

Interpretation/next move: this is a typed in-scope pre-create lifecycle blocker, not a runtime or FP8 result. Do not wrap it ad hoc or create a resource. Resume only with a shared durable typed sequential controller that accepts these scripts, or an explicitly authorized narrow implementation with the required owner/gate tests.

## 2026-07-17 — director authorizes one in-place controller correction

The typed blocker is accepted. Continue in this same project by narrowly extending the shared `mla_microbench_control.py` with a durable provider-owner gate, atomic primary retrieval, typed trigger evaluation, one conditional script, and verified false/error cleanup. Add only the five named behavioral tests. If deterministic local work outlives a response, one 45-minute no-provider systemd owner must emit `artifacts/controller-terminal.json`; no provider create is allowed before that and a refreshed identity preflight pass. Afterward launch directly without another director cycle. The project budget is amended to 75 wall minutes and 3 local CPU-hours; provider exposure, storage, and `$0.50` spend caps are unchanged.

## 2026-07-17 — durable shared-controller consumer session active

Question: can the admitted checkpoint-free pinned-vLLM consumer sequence reach an L40S under one typed durable owner?

Action: extended the named shared controller with the admitted durable-owner gate, `VerifiedRetainedOwner`, watchdog, atomic per-stage retrieval, typed primary trigger, false branch, and conditional stage. `artifacts/controller-terminal.json` records all five focused behavioral tests passing; `artifacts/preflight-20260717T051253Z.json` refreshes immutable hashes. After one zero-instance/zero-disk inventory check, launched the controller as `gemma-fp8-consumer-20260717t051400z.service`.

Handoff: PID `1874796`, cgroup `/user.slice/user-0.slice/user@0.service/app.slice/gemma-fp8-consumer-20260717t051400z.service`, deadline `2026-07-17T05:33:33Z`, artifact root `artifacts/gemma-fp8-consumer-20260717t051400z/`. The owner is active and will create its cleanup watchdog only after provider creation yields an authenticated resource identity. Do not poll, replace, or create another allocation; reconcile its typed stage/summary/cleanup artifacts on the next turn.

## 2026-07-17 — director closes incomplete scientific program

The owner is terminal after 659.202 provider seconds and `$0.138968` derived cost; cleanup reports zero instances and disks, and a fresh authenticated inventory is empty. The retrieved primary archive is useful negative operational evidence, but it contains no timing rows: `Fp8LinearMethod` selected `CutlassFP8ScaledMMLinearKernel`, then construction failed because the benchmark omitted the required current-vLLM-config context. Static inspection also finds unconditional placeholder exceptions instead of the required shape loop and `ParallelLMHead`, while the remote archive omitted the controller's internal `manifest.json`, causing the outer summary to lose the retrieved stage record. This is a final-benchmark contract failure, not FP8/L40S science. Close without retry; the successor W4 component project includes a matched actual-FP8 comparator and must pass the final-staged-program audit before create.
