# Full-47 current background scheduling knee

## Question

On the exact current unchanged GLM-4.7-Flash AWQ identity, do background concurrency 24, 28, or 30 provide a stable throughput improvement over a bracketed c32 control while preserving the campaign's exact 8,192-input/1,024-output workload and 300-second completion envelope?

## Why this is the next decision

The same exact stock identity measured c32 at `596.851973` and later `609.606365` output tok/s, while c36 collapsed to `549.798962`. The campaign needs a direct scheduling-knee measurement between underfilled and saturated/collapsed operation, not another transfer bound. At the fresh `$1.10/L40S-hour` planning rate, the authoritative ordinary and robust gates are `594.466` and `606.355` tok/s; a stable `628` tok/s endpoint would plan at about `$0.487/M` output tokens versus about `$0.501/M` at `609.606`.

This is unchanged-checkpoint performance evidence only. It cannot cure the campaign's unresolved deployable-quality or sustainable-lifecycle requirements.

## Frozen identity

- Checkpoint: `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`.
- `model-files.sha256` file SHA-256 at delegation: `a54799210429cdc73654afc09ba1415d00400061b956bb3e5cb55cf4fc314b58`.
- Runtime: pinned vLLM `0.15.0` image `sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543`.
- Proven lifecycle launcher: `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, delegation SHA-256 `4b27b16b55d721b1c1a8964740ce7a5064146f2aacae8bb921f84026f2193c95`.
- Batched runner: `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/vllm_batched_runner.py`, delegation SHA-256 `0db2de2bd749c18bcd2ca45c16e7b3617daf5307665456b1dac039c81f90fa72`.

Rehash every used input immediately before launch and close pre-create on unexplained drift.

## Execution contract

Provider mutation is blocked until `shared_as_65th_marlin_expert_gate` reaches authenticated zero instance/disk inventory. Then this project becomes the sole provider/spend owner. Use one external-systemd-main scientific controller with proof of durable ownership (`INVOCATION_ID` and `SYSTEMD_EXEC_PID`, or an equivalent harness-owned service) plus one independent absolute cleanup watchdog. A foreground shell PID, new session, or cleanup watchdog alone is not durable scientific ownership.

In the same researcher turn, make only the bounded existing-AWQ-frontier launcher/runner validation change needed to express the literal arm sequence `(32,24,28,30,32)`, freeze and test it, and launch. If that sequence and durable owner cannot be ready in that turn, return a typed pre-create close. Do not return readiness and do not build a project-specific lifecycle/controller successor.

### Cycle 130 fresh re-admission correction

The Cycle 129 researcher correctly returned `PRECREATE_CLOSE_SHARED65_NONZERO_INVENTORY` before packet validation because the named orphan was still live. That is a scheduling null with zero creates and zero science, not evidence about this question. A fresh director admission may reactivate this same project only after independent authenticated zero inventory; do not create an `r2` project or a project-specific wrapper.

The delegated shared runner is not currently capable of this literal bracket: its allowlist rejects the tuple, its runner requires strictly increasing unique concurrency values, repeated c32 artifact names would collide, and its detached watchdog remains in the scientific service's control group. The bounded same-turn implementation must therefore:

- admit only the exact ordered tuple `(32,24,28,30,32)` in this new mode;
- give ordered arms unique identities `c32_pre,c24,c28,c30,c32_post` while preserving the two-wave request count and exact concurrency in every artifact;
- add focused behavioral tests for tuple exclusivity, ordered duplicate-anchor preservation, unique artifact identities, and `2*c` completed requests per arm;
- start the absolute cleanup watchdog as an independent persistent user-systemd unit and record its unit/main-PID identity before science; and
- rehash the controller, runner, remote wrapper, tests, model manifest, and frozen command, then launch under an absolute external-systemd-main scientific owner in that same turn.

If any of those conditions cannot be implemented and tested before provider mutation in the turn, close locally. A new session, foreground PID, or watchdog child in the scientific owner's cgroup is not durable ownership.

Authorize one preemptible Nebius L40S create, at most `$0.60` and `2,400` allocation seconds including cleanup; no retry, repair hold, second create, or post-result retention. Use one unchanged server with `max_num_seqs=32`, `max_num_batched_tokens=65,536`, prefix cache off, BF16 KV, and `num_kv_splits=4`. Each arm sends exactly two complete waves at its named concurrency using the exact 8,192-input/1,024-output workload. Interactive TTFT gates are non-authoritative; every request must complete within 300 seconds.

Capture exact request/token geometry, all completions, prefix-cache zero deltas, semantic and histogram gates, per-arm wall throughput/TTFT/TPOT/queue, server KV/resource identity, peak and steady HBM, power/clocks/utilization, useful/scored/exposure time, immutable archive hashes, derived experimental cost, and authenticated instance/disk cleanup. Operational or capacity failure is terminal evidence, not a retry trigger.

## Decision rule

Let the mean of the two c32 anchors be the control. If the anchors differ by more than `3%`, return `UNSTABLE_CONTROL_CLOSE`. Otherwise promote the best of c24/c28/c30 only if it is at least `606.355` tok/s and at least `1.03x` the bracketed c32 mean. Return `BACKGROUND_KNEE_PASS` with that exact concurrency if both gates pass; otherwise return `SCHEDULING_CLOSE`. Never choose an arm on TTFT or a partial-request result.

Setup, bootstrap, and checkpoint staging are expected to dominate any single arm, but all five arms are preregistered parts of the original scientific workload. No separate adjacent conditional follow-up can reuse only content-bound state and be ready within ten minutes, so clean normally at every endpoint.

## Stop rule

One terminal `BACKGROUND_KNEE_PASS`, `SCHEDULING_CLOSE`, `UNSTABLE_CONTROL_CLOSE`, typed operational/capacity close, or pre-create close. No retry, retained session, follow-up sweep, quality work, provider comparison, or successor preparation.

## Available resources

Use the exact prior stock c32/c36 artifacts, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.
