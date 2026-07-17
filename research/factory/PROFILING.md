# GPU profiling tools

The lab uses one thin command to capture and normalize existing profiler output. It does not provision machines and it is not a replacement for PyTorch/Kineto, Nsight, ROCm profiling tools, DCGM, or serving telemetry.

Researchers can call `research/factory/tools/grad-profile` directly. Installed environments also expose `grad-profile`.

## Fast path

Record host capabilities once per new image, driver, or machine topology:

```bash
research/factory/tools/grad-profile probe --output runs/host-probe.json
research/factory/tools/grad-profile providers
```

Run the warmed profiler-off benchmark first. This is the throughput, latency, energy, and cost truth:

```bash
research/factory/tools/grad-profile capture \
  --tier baseline --backend nvidia --output-root runs \
  --timeout 900 -- python3 benchmark.py
```

Use a short timeline only when a result needs attribution:

```bash
research/factory/tools/grad-profile capture \
  --tier timeline --backend nvidia --output-root runs \
  --timeout 300 -- python3 representative_window.py
```

Use hardware counters only on selected kernels or semantic ranges:

```bash
research/factory/tools/grad-profile capture \
  --tier compute --backend nvidia --output-root runs \
  --kernel-name 'regex:dense.*gemm' --launch-count 10 \
  --timeout 600 -- python3 exact_shape_bench.py
```

For AMD bare metal, keep the same tiers and use `--backend amd`. Timeline capture wraps `rocprofv3`; compute capture wraps `rocprof-compute`. Deep captures fail clearly when the vendor tool is absent. Baseline capture remains usable on CPU-only development hosts.

## Normalize and compare

Export Nsight Systems to SQLite and Nsight Compute to CSV using their native tools, then normalize the artifacts:

```bash
research/factory/tools/grad-profile analyze \
  --run-dir runs/candidate \
  --nsys-sqlite runs/candidate/timeline.sqlite \
  --ncu-csv runs/candidate/compute.csv \
  --benchmark runs/candidate/benchmark.json \
  --semantics runs/candidate/semantics.json

research/factory/tools/grad-profile compare \
  --control runs/control/profile_summary.json \
  --candidate runs/candidate/profile_summary.json \
  --output runs/comparison.json
```

For ROCm timelines, pass the generated `kernel_trace.csv` as `--rocprof-kernel-csv`.

The normalizer calculates kernel interval union separately from summed work, integrates sampled power, derives committed-rate dollars per million output tokens, hashes compiler/codegen artifacts supplied with `capture --artifact`, and reports semantic attribution coverage. It never treats profiler-on timing as serving truth.

A minimal benchmark record is:

```json
{
  "output_tokens_per_second": 304.0,
  "output_tokens_total": 32768,
  "gpu_hourly_usd": 2.95,
  "rate_basis": "committed production planning rate",
  "workload_id": "glm47-aa-matched-v1"
}
```

A minimal semantic record is:

```json
{
  "schema_version": 1,
  "operations": [
    {
      "id": "layer-12-dense",
      "phase": "decode",
      "kernel_patterns": ["dense", "gemm"],
      "shapes": {"m": 8, "n": 4096, "k": 4096},
      "dtype": "fp16",
      "routing": {"active_experts": 1}
    }
  ]
}
```

Use stable NVTX or ROCTx names to join model semantics to kernels. Preserve exact model revision, workload, runtime, compiler, kernel, chip, clocks, power cap, and topology in adjacent experiment artifacts.

## Exact-shape optimization loop

[`data/profiling_shape_atlas.json`](data/profiling_shape_atlas.json) stores reusable exact-shape measurements. Add a result only after the exact operation, model revision, accelerator, runtime/kernel, and metric are known:

```bash
research/factory/tools/grad-profile shape-record --input runs/shape-result.json
```

Use CUTLASS Profiler, NVBench, TritonBench, or a small custom benchmark for NVIDIA shapes; use the corresponding HIP/Triton/ROCm path on AMD. Save PTX, SASS, Triton IR, HSACO metadata, compiler flags, or generated-kernel source with `--artifact` when code generation is part of the hypothesis. The atlas is evidence, not a leaderboard: operator wins must still earn a profiler-off service experiment.

## Collection policy

- Every material experiment: profiler-off benchmark plus low-frequency service and GPU samples.
- Unexplained bottleneck: a few representative requests in PyTorch/Kineto or a vendor timeline.
- Promising critical kernel: selected hardware-counter ranges only.
- Custom kernel: exact-shape benchmark and compiler artifacts; sanitizers for correctness, never timing.
- New host/topology: probe plus `nvbandwidth`, CUTLASS/ROCm roofline calibration, and NCCL/RCCL tests when multi-GPU behavior matters.

Use judgment. The objective is a faster sequence of interpretable experiments, not complete telemetry on every run.

## Provider and access boundary

[`data/providers.json`](data/providers.json) tracks Nebius, RunPod, Scaleway, and Gcore. It stores credential variable names and verified profiler-access status, never values. [`docs/GCORE.md`](docs/GCORE.md) is the Gcore usage guide and daily-refreshed Markdown availability/price snapshot. Nebius VM timeline profiling is verified but deep counters were restricted; all bare-metal counter access remains unverified until tested. Provider provisioning and cleanup remain campaign-owned so this tool cannot accidentally create spend.
