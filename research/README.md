# Research tools

Chip experiments, FPGA inference and hardware publishing live in [hardware](../hardware/README.md). The shared tools below remain here.

- [`lab/`](lab/): Rust simulation, model analysis, and validation tools.
- [`factory/`](factory/): optional research scheduling and shared tools.
- [`experiments/`](experiments/): user-requested conversation traces, thin experiment summaries, and supporting aggregate data/charts.

Historical campaigns and agent reports have been removed. Keep reusable code and test fixtures here. Put new run output in ignored `.agents/runtime/` directories. Do not create dated reports, evidence trees, or campaign logs unless the user requests those deliverables. Update existing documentation only when operation or a useful decision changes.
