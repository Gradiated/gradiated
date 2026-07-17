# Research log

## 2026-07-16 — Director opening handoff

- Objective: decide whether a semantics-preserving pinned-runtime memory change can free at least `622.871 MiB`, the exact robust-admission gap for one additional restored layer at c32.
- Require both memory and a conservative `606.355`-tok/s path; fitting via an unbounded eager/capture slowdown is negative evidence.
- The live depth43 owner is excluded. Do not materialize depth44, mutate shared code, or prepare provider work.

## 2026-07-16 — terminal MEMORY_TAX_CLOSE

Question/action: attributed the parent depth42 c32 envelope from its retained archive, one-second telemetry, exact command, and pinned vLLM source; screened the one source-exact allocation removal, `--enforce-eager`. No CUDA, provider, checkpoint, or shared-code action occurred.

Evidence: c32 peaks at `43,871 MiB` and `686.910494` tok/s. The source/loader reports `16.09 GiB` model load; the mandatory 42-layer c32 32x8K BF16 KV is `12,096 MiB`; and PIECEWISE capture reports `1.31 GiB` (`[1,336.32, 1,346.56] MiB` after log rounding). The observed parent capture list is `[1,2,4,8,16,24,32,40,48,56,64]`; this corrects the project brief's shorter listed policy, but does not create a bounded capture-size saving. vLLM source makes eager skip `capture_model()`, so it removes at least `1,336.32 MiB`, which would clear the `622.871 MiB` capacity gap on memory alone.

Interpretation: eager also disables the performance-critical decode graph path. The only c32 result is graph-enabled at `686.910494` tok/s; no eager c32 result or non-overlap bound exists, so its `80.555494`-tok/s robustness headroom cannot establish `>=606.355`. All remaining residual/workspace/allocator attribution is unidentifiable for a conservative `>=622.871 MiB` semantic-saving claim. Terminal `MEMORY_TAX_CLOSE`; do not materialize depth44 or prepare a successor.

Artifact: [`artifacts/MEMORY_TAX_CLOSE_2026-07-16.json`](artifacts/MEMORY_TAX_CLOSE_2026-07-16.json).
