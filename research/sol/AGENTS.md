# Inference Foundry Development Instructions

- Continue autonomously through reversible, in-scope engineering and research decisions. Do not ask the user to select the next test, approve a safe retry with a materially changed hypothesis, inspect routine output, or confirm an evidence-backed choice.
- A failed placement, provider/API fault, unavailable GPU, incompatible runtime, negative result, or killed hypothesis is evidence about one lineage, not a campaign blocker. Preserve it, pivot to the next highest-information admissible lineage, and keep going until the campaign objective reaches its defined decision gate or budget/time cap.
- Escalate only for authority that is genuinely absent: new credentials, spending beyond the authorized cap, destructive or irreversible external changes, material expansion beyond the stated workstream, or safety/legal risk. Exhaust safe alternatives before escalation.
- Use test-driven development: write a failing behavioral test, implement the minimum change, then refactor.
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
