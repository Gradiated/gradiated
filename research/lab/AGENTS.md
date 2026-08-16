# Inference Foundry Development Instructions

- Continue autonomously through reversible, in-scope engineering and research decisions. Do not ask the user to select the next test, approve a safe retry with a materially changed hypothesis, inspect routine output, or confirm an evidence-backed choice.
- Research progress is valid model/workload evidence and decisions, not preparation. Treat an assigned project brief and its content-bound references as the director's admission decision. Check mutable launch facts once in a grouped command, then run; revisit history only when a current observation contradicts it.
- A failed placement, provider/API fault, unavailable GPU, incompatible runtime, negative result, or killed hypothesis is evidence about one lineage, not a campaign blocker. If the workload never reached the GPU, prefer one material correction or the last launcher that produced a valid result, then continue with a fresh matched control.
- Escalate only for authority that is genuinely absent: new credentials, spending beyond the authorized cap, destructive or irreversible external changes, material expansion beyond the stated workstream, or safety/legal risk. Exhaust safe alternatives before escalation.
- Provider GPUs are lab-owned warm benches recorded in `research_lab/runtime/gpus.json`, not project resources. The director allocates and performs provider teardown. Researchers atomically claim compatible benches with `python3 -m grad_research.gpu_pool`, reuse resident images/checkpoints/models/caches, patch ordinary defects in place, update the resident description, and release without cleanup. Keep one lab lifecycle owner plus an absolute watchdog per bench. The periodic supervisor compares provider reality with the inventory; it may fence an objectively expired, unsafe, or ownerless registered bench by marking it draining, then wakes the director for cleanup. Never auto-steal a stale claim; the director reclaims it to maintenance after inspection. Fully verify immutable weights once per unchanged storage identity and hash every experiment artifact independently.
- Capture enough setup, steady-state, request, quality, service, GPU, and cost telemetry to interpret the result and choose the next experiment. Add deeper counters only when they discriminate the next decision; observability is not a reason to delay an otherwise credible run.
- Use a cheap bound, simulation, or exact-shape microbenchmark when it reaches a decision materially faster than a full server run. Do not force a long fidelity ladder when a bounded target-GPU measurement is the fastest credible falsifier. Never treat summed overlapping kernel time as wall-time share.
- A claim owns experiment mutation on one bench; the director owns provider spend and cleanup. Independent benches may run concurrently whenever the director judges that added decision speed justifies the spend. Queue compatible projects on resident state instead of rebuilding it, without blocking unrelated GPU work.
- Keep the user-selected main coordinator model. Reserve high reasoning for opportunity selection, causal interpretation, scientific gates, and unexpected failures. Use faster or lower-effort workers for disjoint mechanical tasks such as log parsing, fixtures, packaging, routine tests, and provider polling; use at most one high-reasoning adversarial reviewer per decision.
- Batch repeated shell operations into bounded scripts with structured output. Prefer one yielded provider command over frequent model-driven polling. Reuse settled image, dependency, key, and parser evidence; validate only what changed. Timestamp setup and scientific phases and report `useful_gpu_seconds` separately from provider-active exposure when available.
- Generate a daily throughput report with `.agents/skills/experiment-run/scripts/research_efficiency.py`. Improve valid scientific outcomes per active coordinator hour and dollar; do not optimize speed metrics by weakening controls, telemetry, artifact retrieval, or cleanup.
- Keep the system deterministic. Every experiment must be reproducible from its specification and seed.
- For reusable code changes, write the narrowest failing behavioral test, implement the fix, then refactor. Do not turn the test workflow into a separate readiness phase for an already admitted experiment.
- Do not add comments unless the intent cannot be made clear through names and structure.
- Prefer small typed contracts over shared mutable state.
- Do not panic in library code for user-controlled input.
- Run `cargo fmt --check`, `cargo clippy --workspace --all-targets -- -D warnings`, and `cargo test --workspace` for completed changes.
- Commit completed changes directly to `main` with standard Git. Do not create a feature branch or pull request unless the user explicitly requests one.

## Module ownership

- `spec`: versioned experiment inputs, validation, and content identity.
- `performance`: analytical and external performance-oracle contracts.
- `simulation`: request scheduling and event simulation.
- `economics`: activity-based input/output cost accounting.
- `search`: candidate generation, constraints, ranking, and Pareto results.
- `foundry-cli`: file I/O and user-facing commands only.
