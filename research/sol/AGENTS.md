# Inference Foundry Development Instructions

- Continue autonomously through reversible, in-scope engineering and research decisions. Do not ask the user to select the next test, approve a safe retry with a materially changed hypothesis, inspect routine output, or confirm an evidence-backed choice.
- Research progress is valid model/workload evidence and decisions, not preparation. Treat an assigned project brief and its content-bound references as the director's admission decision. Check mutable launch facts once in a grouped command, then run; revisit history only when a current observation contradicts it.
- A failed placement, provider/API fault, unavailable GPU, incompatible runtime, negative result, or killed hypothesis is evidence about one lineage, not a campaign blocker. If the workload never reached the GPU, prefer one material correction or the last launcher that produced a valid result, then continue with a fresh matched control.
- Escalate only for authority that is genuinely absent: new credentials, spending beyond the authorized cap, destructive or irreversible external changes, material expansion beyond the stated workstream, or safety/legal risk. Exhaust safe alternatives before escalation.
- For GPU sessions with material image/checkpoint/model setup, queue arms and retain the allocation across in-place repairs or follow-ups that can start within ten minutes. Reuse the live server for observer changes and the resident checkpoint/image for server changes. Fully verify immutable weights once per session and reuse a content-addressed integrity marker only while its storage identity and metadata fingerprint remain unchanged; still hash every arm artifact independently. A typed envelope containing a nested harness error is not a completed scientific result. Keep one owner plus an absolute cleanup watchdog, and perform verified teardown only when the session ends.
- Capture enough setup, steady-state, request, quality, service, GPU, and cost telemetry to interpret the result and choose the next experiment. Add deeper counters only when they discriminate the next decision; observability is not a reason to delay an otherwise credible run.
- Use a cheap bound, simulation, or exact-shape microbenchmark when it reaches a decision materially faster than a full server run. Do not force a long fidelity ladder when a bounded target-GPU measurement is the fastest credible falsifier. Never treat summed overlapping kernel time as wall-time share.
- Use one coordinator for provider mutation, spend, retained state, and cleanup. Parallelize trace analysis, prior-art review, simulators, candidate generation, tests, artifact audit, and conditional preregistration. Run parallel GPU allocations only when independent ownership and added decision speed justify the extra spend; otherwise queue arms on one retained allocation.
- Keep the user-selected main coordinator model. Reserve high reasoning for opportunity selection, causal interpretation, scientific gates, and unexpected failures. Use faster or lower-effort workers for disjoint mechanical tasks such as log parsing, fixtures, packaging, routine tests, and provider polling; use at most one high-reasoning adversarial reviewer per decision.
- Batch repeated shell operations into bounded scripts with structured output. Prefer one yielded provider command over frequent model-driven polling. Reuse settled image, dependency, key, and parser evidence; validate only what changed. Timestamp setup and scientific phases and report `useful_gpu_seconds` separately from provider-active exposure when available.
- Generate a daily throughput report with `.agents/skills/experiment-run/scripts/research_efficiency.py`. Improve valid scientific outcomes per active coordinator hour and dollar; do not optimize speed metrics by weakening controls, telemetry, artifact retrieval, or cleanup.
- Keep the system deterministic. Every experiment must be reproducible from its specification and seed.
- For reusable code changes, write the narrowest failing behavioral test, implement the fix, then refactor. Do not turn the test workflow into a separate readiness phase for an already admitted experiment.
- Do not add comments unless the intent cannot be made clear through names and structure.
- Prefer small typed contracts over shared mutable state.
- Do not panic in library code for user-controlled input.
- Run `cargo fmt --check`, `cargo clippy --workspace --all-targets -- -D warnings`, and `cargo test --workspace` for completed changes.
- Use GitButler for repository operations. Do not use `git checkout`, `git branch`, `git switch`, `git push`, or `git commit`.

## Module ownership

- `spec`: versioned experiment inputs, validation, and content identity.
- `performance`: analytical and external performance-oracle contracts.
- `simulation`: request scheduling and event simulation.
- `economics`: activity-based input/output cost accounting.
- `search`: candidate generation, constraints, ranking, and Pareto results.
- `foundry-cli`: file I/O and user-facing commands only.
