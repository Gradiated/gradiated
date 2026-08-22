# Gemma 4 target-verification cross-operator persistent executor

## Question

Can a request-owned persistent or task-graph executor reduce compulsory
launches, intermediate HBM traffic, and scheduler gaps across the exact Gemma
4 M=384 target-verification hot block while preserving target, request, paged
KV, acceptance, and commit semantics?

## Why this matters

The campaign needs approximately 20% lower sustainable cost than the fixed
qualified H200 result. The current attention experiment exposed a large,
regular 32-request x 12-row verification wave but failed before CUDA because
its producer contract required an absent full checkpoint. That failure does
not test the materially different cross-operator opportunity named in
`CAMPAIGN.md`: retaining request-owned work across RMSNorm, dynamic FP8,
linears, attention/MLP, residual, target head, acceptance, and KV commit.

## Bound evidence

- Exact checkpoint: `google/gemma-4-31B-it` at
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Scope: c32 NGRAM target verification, M=384, 32 requests x 12 rows, TP1.
- Read only the current source/physical bindings:
  `../gemma4_h200_m384_target_verify_attention_executor/SOURCE_TRACE.json`
  (`dffeb697…`) and
  `../gemma4_h200_m384_target_verify_attention_executor/PHYSICAL_MODEL.json`
  (`c9249702…`).
- The attention kernel, producer acquisition, and prior owner repairs are out
  of scope; this project owns the cross-operator execution boundary.

## Scope and result

Trace the pinned runtime from the first target-row normalization through the
first exact acceptance/KV-commit consumer. Quantify compulsory bytes,
launches, grid waves, synchronization, state lifetime, and the maximum
whole-request fraction that a request-owned executor can remove. Test at least
three legal boundaries, including one that retains FP8 scale/dataflow and one
that spans the target-head/acceptance seam.

Publish `MECHANISM_TERMINAL.json` containing either:

- a concrete source-level persistent/task-graph hot-block implementation,
  deterministic CPU/reference oracle, exact state-machine trace, and a bounded
  H200 discriminator contract; or
- a typed source, semantic, or physical negative identifying the first
  unavoidable materialization or synchronization boundary.

The implementation must execute a real exact-shape CPU/reference consumer; a
diagram, wrapper, metadata hook, or generic executor design is not a result.

## Resources and limits

- Zero GPU and zero provider spend.
- Wall-clock budget: 90 minutes.
- Storage budget: 2 GiB.
- Use `$researcher` with deep profile, `$kernel-research`, and
  `$experiment-run`.
- Do not claim a bench, invoke CUDA, reserve spend, inspect the failed
  attention owner lineage, retry attention, run endpoint science, or mutate
  provider lifecycle.
