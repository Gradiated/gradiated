# NGRAM fixed-tree target-verification attention

## Question

Can one H200-specialized attention/dataflow path for the exact native-NGRAM
target-verification shape reduce sustainable c32 service time below the
measured `0.625149101968745 s/request` while preserving the already-qualified
decode-equivalent target semantics?

## Evidence and mechanism

The repaired exact-c32 trace closes host bookkeeping and LM-head
materialization as leading opportunities. Across 15 target-verification
steps, the trace contains exactly 900 Triton `_fwd_kernel` launches
(`60 layers * 15 steps`) totaling `1,488,205.758 us`, or `62.66%` of the
`2,375,141.908 us` repaired trace window. Each launch used a
`[32, 32, 1]` grid, 256 threads, 255 registers/thread, and 81,920 bytes of
shared memory. GPU interval union was `93.354%`; host/cache-slot preparation
was only `3,133 us`. The consumed depth-major LM-head pair instead regressed
service time by `3.46%` and changed 22/32 response texts.

The fixed target geometry is c32 with 12 draft tokens/request, hence 384
query positions per verification step, page size 1, FP8 E5M2 KV cache, BF16
model activations, 32 query heads, 16 KV heads, head dimension 256, and 60
layers comprising 50 sliding-window-1024 and 10 full-attention layers. The
current pinned runtime routes NGRAM target verification through its
prefill/tree-mask attention construction.

## Experiment

Use `$kernel-research`. Before a paid claim, mechanically bind the repaired
trace, exact launch, model config, tree mask and paged-KV index construction,
and the pinned Triton prefill `_fwd_kernel` source reached by
`NgramVerifyInput`. Freeze one immutable packet implementing exactly one
fixed-tree target-verification attention/dataflow intervention for SM90. It
must preserve the custom causal tree mask, local/full layer semantics,
positions, page-1 KV addressing, FP8 E5M2 KV values, BF16 query/output
contract, target logits, and accepted tokens.

Atomically claim only warm bench
`h200-ngram-critical-e00bwcwgsxawx1jmgw`. Use the resident image and
checkpoint. First run an exact-consumer correctness/timing component against
the installed Triton prefill control at the bound 32-request, 12-draft-token
shape. The component must cover one sliding layer and one full-attention layer,
adversarial tree-mask boundaries, and real paged-KV indices. Collect only the
minimum counters needed to distinguish reduced attention time, launch count,
and bytes from a resource-limit or synchronization shift.

Only a correct component with a positive whole-request bound may admit one
fresh matched profiler-off c32 control/candidate pair. Use a detached durable
remote owner, keep ordinary compile/API/retrieval repairs inside one claim,
and persist a typed terminal before release. Do not replay the consumed
LM-head intervention, quality suite, verifier discriminator, or accepted-token
suite. Do not change NGRAM depth/settings, concurrency, model precision,
attention semantics, backend flags, or run a kernel/tile/split sweep.

## Decision

Retain only if all exact-consumer rows pass, all 32 requests complete,
accepted token IDs and normalized responses match, finish reason and usage
match, candidate service time improves over its fresh control, p95 does not
materially regress, and the measured `_fwd_kernel` reduction explains the
whole-request gain. A compile failure after bounded repair, semantic mismatch,
non-positive component bound, or non-positive matched pair closes this one
fixed-tree realization.

## Resources

- Priority: `6795`
- Researcher profile: `deep`
- Authorized cumulative spend: `$6`
- Compute: the retained H200, at most 110 claimed GPU-minutes
- Wall clock: release by `2026-07-24T14:20:00Z`
- Storage: at most 10 GiB of new project-local artifacts
- Provider mutation: forbidden
