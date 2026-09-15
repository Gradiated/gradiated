# Inference Foundry

Rust tools for model representation, serving simulation, hardware estimates, and inference economics. The analytical outputs are estimates; they do not establish measured serving performance.

- `crates/`: core library, command-line tool, and tests.
- `configs/`: model and simulation inputs.
- `experiments/`: a small set of retained fixtures read by tests and configurations. Historical campaign workspaces have been removed.
- `validation/`: local model and simulator validation tools.
- `docs/`: reference documentation.
- [`ARCHITECTURE.md`](ARCHITECTURE.md): module boundaries.
- [`../factory/`](../factory/): optional research scheduling tools.

Run checks from this directory:

```sh
cargo fmt --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

Keep new run output under the repository's ignored `.agents/runtime/` directory. Do not write new campaign output into the retained fixture paths. Add reusable fixtures only when a test needs them.
