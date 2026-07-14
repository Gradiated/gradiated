# Inference Foundry Development Instructions

- Continue autonomously through reversible, in-scope engineering and research decisions. Do not ask the user to select the next test, approve a safe retry with a materially changed hypothesis, inspect routine output, or confirm an evidence-backed choice.
- A failed placement, provider/API fault, unavailable GPU, incompatible runtime, negative result, or killed hypothesis is evidence about one lineage, not a campaign blocker. Preserve it, pivot to the next highest-information admissible lineage, and keep going until the campaign objective reaches its defined decision gate or budget/time cap.
- Escalate only for authority that is genuinely absent: new credentials, spending beyond the authorized cap, destructive or irreversible external changes, material expansion beyond the stated workstream, or safety/legal risk. Exhaust safe alternatives before escalation.
- Use test-driven development: write a failing behavioral test, implement the minimum change, then refactor.
- For GPU sessions with material image/checkpoint/model setup, queue arms and retain the allocation across in-place repairs or follow-ups that can start within ten minutes. Reuse the live server for observer changes and the resident checkpoint/image for server changes. Fully verify immutable weights once per session and reuse a content-addressed integrity marker only while its storage identity and metadata fingerprint remain unchanged; still hash every arm artifact independently. A typed envelope containing a nested harness error is not a completed scientific result. Keep one owner plus an absolute cleanup watchdog, and perform verified teardown only when the session ends.
- Before testing a trace-selected custom kernel in a full model server, prefer a correctness-checked standalone microbenchmark with the exact model shapes and hardware resource limits. Reject illegal tile/launch configurations cheaply and require a prospective component-to-end-to-end threshold.
- Maintain a cross-stack observation-to-opportunity register for model research. Every intervention must trace to a measured symptom or explicit analytical bound, list competing explanations and a cheapest falsifier, and update the residual bottleneck after measurement. Never treat summed overlapping kernel time as wall-time share.
- Maximize decision-relevant observability: separate setup from steady state and, where relevant, capture request distributions, scheduler iteration/batch/KV state, CPU/GPU timelines, kernel shapes and launch resources, HBM/L2/occupancy/stalls, VRAM, power, collectives/network, expert skew, MTP acceptance, cache behavior, failures, quality, SLO, and total allocation cost. Record unavailable signals explicitly.
- Climb the fidelity ladder before expensive hardware: bounds and roofline, deterministic simulation, independent reference oracle, reduced-model/trace replay, exact-shape component harness, target-hardware microbenchmark, then matched serving A/B and provider comparison. Lower-fidelity success only promotes the next measurement; lower-fidelity failure may kill the lineage.
- Use one coordinator for provider mutation, spend, retained state, and cleanup. Parallelize trace analysis, prior-art review, simulators, candidate generation, tests, artifact audit, and conditional preregistration. Run parallel GPU allocations only when independent ownership and added decision speed justify the extra spend; otherwise queue arms on one retained allocation.
- Keep the user-selected main coordinator model. Reserve high reasoning for opportunity selection, causal interpretation, scientific gates, and unexpected failures. Use faster or lower-effort workers for disjoint mechanical tasks such as log parsing, fixtures, packaging, routine tests, and provider polling; use at most one high-reasoning adversarial reviewer per decision.
- Batch repeated shell operations into bounded scripts with structured output. Prefer one yielded provider command over frequent model-driven polling. Before paid compute, locally validate the image, dependency/key fingerprints, capability-output fixtures, and parser behavior. Every allocation must timestamp setup phases and report `useful_gpu_seconds` separately from provider-active exposure.
- Generate a daily throughput report with `.agents/skills/experiment-run/scripts/research_efficiency.py`. Improve valid scientific outcomes per active coordinator hour and dollar; do not optimize speed metrics by weakening controls, telemetry, artifact retrieval, or cleanup.
- Keep the system deterministic. Every experiment must be reproducible from its specification and seed.
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
