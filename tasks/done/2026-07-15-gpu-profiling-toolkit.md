# GPU profiling toolkit

Date: 2026-07-15
Lane: product/research infrastructure
Status: complete
Issue: https://github.com/joshsny/gradiated/issues/22

## Objective

Give research-factory agents a small provider-neutral toolkit for profiling model-serving runs on counter-capable bare-metal GPUs without making deep profiling part of every experiment.

## Behavior contract

- User: research director and delegated researchers.
- Inputs: a command, capture tier, runtime/model/workload metadata, optional semantic geometry, and an external provider/machine allocation.
- Outputs: an immutable run manifest, command/stdout/stderr, low-overhead GPU samples, native profiler artifacts, normalized JSON/Markdown summary, and reusable exact-shape records.
- Failure: preserve partial artifacts and the child exit status; never report a profiler capture as a scoreable service result; never print or persist credential values.
- Persistence: repository owns schemas, code, provider metadata, and documentation; experiment directories own generated run artifacts; external secret stores own credentials.

## Delivered

- `research/factory/tools/grad-profile` with `probe`, `providers`, `capture`, `analyze`, `compare`, and `shape-record` commands.
- Profiler-off baseline capture with optional NVIDIA sampling and secret-redacted manifests.
- NVIDIA Nsight Systems/Compute and AMD rocprofv3/ROCm Compute Profiler capture paths.
- PyTorch Chrome, Nsight Systems SQLite, Nsight Compute CSV, and rocprofv3 kernel-trace normalization.
- Overlap-safe interval-union timing, semantic attribution, multi-GPU energy integration, profiler perturbation, and committed-rate $/token comparisons.
- Exact-shape/codegen artifact hashing and a shared append-only shape atlas.
- Nebius, RunPod, and Scaleway provider/access registry containing credential variable names only.
- Researcher guidance and a concise profiling operating guide.
- Wafer resource-map review incorporated into the profiling ecosystem decision.

## Verification

- 10 focused profiling/provider tests pass.
- CLI CPU-only capture and host probe smoke tests pass.
- Python compilation, `python3 tools/devex/check.py`, and scoped `git diff --check` pass.
- Factory suite: 77 pass and 2 unrelated historical-state tests fail because the GLM campaign ledger has advanced from the expected split-8/calibration state to V37.

## External assumptions

- Deep counter captures will run on bare metal with root/driver access.
- Provider credentials will be supplied later outside the repository.
- Nebius and RunPod remain usable experiment providers; Scaleway is registered but unavailable until credentials and access are supplied.
