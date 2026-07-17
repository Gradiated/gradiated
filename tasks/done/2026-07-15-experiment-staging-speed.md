# Task: 2026-07-15-experiment-staging-speed

## Outcome

The proven Nebius GLM launcher reaches its first scientific arm faster and loses less work when setup is interrupted. Checkpoint staging resumes at file granularity, transfer deadlines scale with payload size, retained hosts reuse an exact runtime image, failed runs do not idle for ten minutes unless a repair window is explicitly requested, and lifecycle telemetry makes the remaining setup share measurable.

## Owner and coordination

- GitHub issue: https://github.com/joshsny/gradiated/issues/16
- GitHub project: unavailable to the configured fine-grained token; issue is canonical
- owner: Codex
- Codex thread: current user-directed session
- created: 2026-07-15T19:45:00Z
- started: 2026-07-15T19:45:00Z
- last updated: 2026-07-15T20:20:00Z
- scope: `research/sol/experiments/glm47flash/campaign_100/nebius/` and focused tests/documentation
- excluded paths: provider APIs, new credentials, paid allocations, checkpoint contents, unrelated live research artifacts
- dependencies: existing OpenSSH/SCP client, proven Nebius launcher, current content-addressed model manifests

## Contract

- hypothesis or user value: File-resumable staging, exact retained-image reuse, and eliminating unconditional failure holds will materially reduce allocation-to-arm time and setup-only exposure without adding an orchestration system.
- acceptance checks: interrupted transfer plans preserve complete files and retransmit only missing/truncated files; timeout scales for 20.17 GB AWQ and 62.44 GB BF16 payloads; a matching remote integrity marker permits a zero-byte staging hit; bootstrap skips a matching labeled derived image and retries cold pulls once; repair waiting defaults to zero and remains explicitly bounded; launcher emits typed phase durations and reserves retrieval time before the provider watchdog.
- quality gate: focused unit tests, all GLM campaign tests, Python compilation, repository DevEx check, and `git diff --check`.
- SLO or budget: zero provider mutation and zero paid compute during implementation; no new Python dependency; no extra network round trip when a verified retained marker is present beyond the grouped state query.
- timeout: focused tests under 60 seconds; implementation stops short of unverified Nebius snapshot/custom-image support.
- artifact locations: source and tests under `research/sol/experiments/glm47flash/campaign_100/`; this task packet records the durable handoff.
- resume command: `python3 -m unittest research/sol/experiments/glm47flash/campaign_100/tests/test_nebius_session_staging.py research/sol/experiments/glm47flash/campaign_100/tests/test_nebius_vllm_smoke_control.py -v`
- rollback or cleanup: source-only changes; no external resources are created.

## Plan

1. Add a small checkpoint staging module and behavioral tests.
2. Integrate it into the proven vLLM launcher after the active paid run releases the file.
3. Add exact retained-image reuse, explicit repair-window opt-in, artifact reserve, and phase telemetry.
4. Run focused and workstream checks and report measured/modelled impact separately.

## Result

- status: complete
- verification: 258 GLM campaign tests pass with `PYTHONPATH=research/factory/src`; 3 research-efficiency tests pass; generated host bootstrap passes `bash -n`; launcher CLI loads; Python compilation, `python3 tools/devex/check.py`, and `git diff --check` pass. Measured unchanged local validation improved from 21.673 s to 0.001 s for AWQ and 63.056 s to 0.020 s for BF16 after the first full-byte validation.
- changed paths: `.agents/skills/experiment-run/scripts/{research_efficiency.py,test_research_efficiency.py}`; `research/sol/experiments/glm47flash/campaign_100/nebius/{session_staging.py,awq_smoke_control.py,vllm_smoke_control.py,vllm_recover_existing.py,remote_vllm_awq_smoke.sh}`; `research/sol/experiments/glm47flash/campaign_100/tests/{test_nebius_session_staging.py,test_nebius_vllm_smoke_control.py}`; this task packet.
- limitations or blocked paths: cross-VM custom images, snapshots, and persistent-disk attach remain unimplemented because the current Nebius path does not bind reliable executable semantics for them. Runtime-image and checkpoint zero-byte reuse apply to retained hosts. The required Sol Rust clippy chain is blocked by an unrelated pre-existing dead-code warning at `crates/foundry-core/src/qwen_int4_kernel.rs:1171`; formatting reached clippy before that failure.
- commit:
- next action: judge the next paid run by the new phase timings, staging reuse bytes, useful GPU seconds, and allocation-to-first-arm time; use `--repair-window-seconds` only when a concrete in-place repair is already available.
