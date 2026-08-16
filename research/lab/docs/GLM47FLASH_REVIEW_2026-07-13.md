# GLM-4.7-Flash independent measurement review — 2026-07-13

## Finding

No GLM-4.7-Flash experiment currently supports a business or economic win claim. The reusable contract in [`validation/real_gpu_campaign`](../validation/real_gpu_campaign/README.md) rejects the harvested attempt as invalid and is designed to reject the same evidence gaps in future runs.

## Evidence reviewed

- `glm47flash/attempt3.tar.gz`, SHA-256 `5a62067ee3ef8f61a1f13f3b1dc90a41ddc0a0585e69e77ae263c1137cf96d1e`.
- The archive has 954 one-second-ish `nvidia-smi` samples, but no header or phase labels. A diagnostic parse gives hardware-busy utilization mean 0.102% (95% CI half-width 0.193 percentage points) and power 72.44 W (0.329 W half-width). Because the samples cover only part of the 3,617.75-second allocation and have no phase identity, the conservative whole-allocation diagnostic is 0.027%; it is not a valid phase or fleet utilization result. Commercial fleet utilization remains unknown.
- The artifact contains no benchmark JSON, both benchmark clients timed out waiting for `/v1/models`, both SGLang metric files are empty, and server logs show `Glm4MoeLiteForCausalLM` falling back to Transformers before failing on unsupported TP style `mla_kv_a_proj`.
- The ledger records attempt 2 at $0.2591 and attempt 3 at $3.0047 of conservative allocation spend. Attempt 3's later manual-harvest record ($1.5520) conflicts with the final one-hour timeout ledger record; the larger final allocation record is retained for conservative accounting. Attempt 1 has a creation record but no completed allocation/teardown accounting and is therefore not silently estimated.

## Hard validation outcome

The validator reports missing identity, provenance, all phase markers, server health, complete teardown evidence, workload/SLO identity, SGLang metrics, and benchmark result. It also reports incomplete phase-level utilization summaries. Economic win permission is false. No TTFT, TPOT, throughput, error rate, `$ / input token`, `$ / output token`, or 8:1 output-equivalent cost can be computed from this campaign; publishing an anchor would be a provenance error.

## Required capture before the next result is admissible

1. Freeze and hash model revision/checkpoint, tokenizer, serving image or source build, CUDA/driver/framework versions, hardware topology, exact command line, seed, and workload file. Record provider price source and capture date separately from measured results.
2. Emit `contract.json` before allocation with the exact workload identity, input/output token distribution, concurrency matrix, SLO thresholds, quality gate, candidate/control identity, and measured-only result provenance.
3. Mark every phase start and finish across the entire allocation, including failed startup and teardown. Each phase must carry counters for expected, observed, succeeded, failed, timed out, dropped, retried, and missing requests; nonzero or unknown missing counters invalidate an economic claim.
4. Capture SGLang `/metrics` for every serving configuration and server exit/health status. Abort benchmarks immediately when the server exits; preserve stderr/stdout and the failed result marker.
5. Record per-request or lossless aggregate benchmark output with input/output tokens, success/failure counts, TTFT, TPOT, end-to-end latency percentiles, throughput, and SLO goodput. A benchmark client timeout is a failed experiment, never zero throughput.
6. Sample GPU telemetry with timestamp, GPU UUID, phase, utilization, memory, power, temperature, and clocks continuously from allocation start through teardown. Report hardware busy utilization by phase, whole-allocation utilization including uncovered time, and commercial fleet utilization only from fleet-level evidence.
7. Create a SHA-256 manifest for every result, telemetry, metrics, log, environment, model identity, and source artifact. Validate local archive hash against the remote hash before accepting it.
8. Compute conservative spend from provider-billed allocation seconds and the exact dated provider rate. Report `$ / input token`, `$ / output token`, and `$ / (output + input/8)` only from measured token counters. Attach uncertainty from repeated runs/bootstrap or a predeclared confidence method.

## Comparison rule

The Lambda SGLang and Cloudflare figures in `glm47flash/REPORT.md` remain published anchors with their own dates and denominators. They cannot be used as fleet throughput or local measured cost. A future comparison must state exact provider price provenance/date and must not combine published performance with measured local performance inside one win claim.
