# NGRAM QLEN-only target-verification mask

## Question

Can the qualified H200 NGRAM endpoint replace its process-wide full-prefix
custom attention mask with the native `12 x 12` query-suffix tree mask and
reduce c32 service time while preserving exact target-verification semantics?

## Evidence and mechanism

The pinned NGRAM worker still sets `USE_FULL_MASK = True`. At every target
verification step it creates one prefix-sized all-ones tensor per request,
concatenates the `12 x 12` tree suffix, and passes a custom mask of roughly
`32 * 12 * (4214 + 12) = 1.62 million` booleans at the representative c32
shape. The same source says a QLEN mask is about 8% faster and that its
consumer must change correspondingly.

The qualified endpoint uses the pinned Triton prefill/decode backends, not
FlashInfer attention. Its target-verify path already skips applying the custom
mask to prefix attention, but `TritonAttnBackend` still computes mask offsets
as `12 * (seq_len + 12)` and the extend kernel indexes the suffix through the
full-prefix stride. The candidate is therefore one representation/dataflow
change: retain only the official `12 x 12` tree mask, make target-verify mask
indptr advance by `12 * 12`, and index the extend suffix with query-length
stride while leaving prefix attention unmasked.

This is distinct from the closed tree-attention tile line and variable-row
compaction. The M16/M32 experiments changed `BLOCK_M` and failed the sliding
numerical oracle; variable compaction removed target rows and was slower and
inexact. This project changes neither query rows nor the stock M64 attention
tile. The repaired trace attributes 900 Triton `_fwd_kernel` launches across
15 verification steps to 62.66% of the c32 trace window, while the NGRAM
quality terminal already passes GPQA-Diamond and TauBench exactly against AR.
The retrieved wave trajectory further establishes that 32 full waves are
capacity-stable; a positive c32 result therefore increases the sustainable
economic margin of the retained background policy.

## Experiment

Use `$kernel-research`. Hash-check `DIRECTOR_BINDING.json`, then inspect the
bound pinned sources and freeze exactly one QLEN-only intervention:

- preserve the official `reconstruct_indices_from_tree_mask` producer and its
  `12 x 12` mask bytes;
- remove only full-prefix all-ones materialization in `NGRAMWorker`;
- update only the Triton target-verify mask buffer/indptr and extend-attention
  custom-mask addressing required by that representation;
- preserve prefix attention as implicitly allowed, and preserve the exact
  custom tree mask over the 12 query/key suffix positions;
- do not change the FlashInfer backend, stock M64 tile, query rows, KV
  ownership, model/NGRAM settings, or scheduler.

Before claiming, freeze the candidate sources and a component consumer. Then
atomically claim only warm bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`, use its resident checkpoint, image,
and caches, and keep one durable controller-host owner responsible for claim
heartbeats, retrieval, and release.

First run an exact c32 target-verify component against the installed stock
control. It must cover one 1024-token sliding layer and one full-attention
layer with real page-1 FP8-E5M2 KV indices, BF16 queries/outputs, representative
4214-token prefixes, and adversarial branching masks. Require exact mask
meaning, target logits within the unchanged control oracle, accepted-token
identity, and a positive measured whole-request bound. Record full versus
QLEN mask bytes, allocations/copies, mask-preparation time, attention time,
and only the minimum causal counters needed to explain the result.

Only a correct positive component may admit one fresh profiler-off matched
c32 control/candidate pair. Require 32/32 accounting, exact emitted token IDs,
normalized responses, finish reasons and usage, plus actual service time and
p95. Ordinary compile, import, observer, server, or retrieval defects remain
inside the same claim and project; localize an unexpected semantic difference
at the first mask/logit boundary before closing it.

Do not replay the verifier discriminator, ten-row suite, production quality,
10K, rolling stream, wave trajectory, attention tiles, or variable
compaction. Run no backend, mask form, tile, NGRAM-setting, concurrency, or
scheduler sweep.

## Decision

Retain the QLEN representation if the exact component passes and the matched
c32 candidate is faster than its fresh control without p95, reliability, or
semantic regression. Any reproducible positive exact gain is decision
relevant because it compounds the already-qualified wave policy.

A non-positive component bound, irreparable mask/logit mismatch, or
non-positive matched pair closes only this QLEN-only Triton realization.
Preserve all sources, exact consumer rows, counters, endpoint rows, hashes,
and a typed terminal before release.

## Resources

- Priority: `7300`
- Researcher profile: `deep`
- Authorized cumulative spend: `$6`
- Bench: retained `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`
- Compute: at most 40 claimed H200-minutes
- Wall clock: complete and release by `2026-07-24T16:45:00Z`
- Storage: at most 10 GiB of new project-local artifacts
- Provider mutation: forbidden

## Director continuation — stock production branch

The observer-v3 endpoint did not exercise the branch its exact component
proved. Its hash-bound launch omitted `--enable-deterministic-inference`, so
`TritonAttnBackend.forward_extend` selected the normal two-stage
`extend_attention_fwd` branch; observer-v3 proved only
`_forward_extend_unified`. This branch mismatch makes the zero audit rows and
semantic mismatch an invalid integration observation, not a QLEN result.

Consume `DIRECTOR_PRODUCTION_BRANCH_REPAIR.json`. Preserve the stock launch
settings and do not force deterministic inference. Freeze exactly one
two-stage QLEN consumer, then use the first real c32 NGRAM Q12
target-verification call as the component: bind its actual prefix/suffix,
mask/indptr, page-1 E5M2 KV, and layer geometry; prove the branch identity;
and compare the stock full-prefix mask with the QLEN-only candidate on the
same captured call. Require nonzero production-path audit rows, exact output
and first-logit equivalence under the existing oracle, exact accounting, and
a positive measured whole-request bound.

Only that exact positive result admits one candidate-only c32 endpoint
against persisted control `0.6049806232813353 s/request`. Require 32/32
completion, nonzero two-stage candidate audit rows, exact token IDs,
normalized text, finish reasons and usage, lower service time, and no p95
regression. Replay no control, unified component, ring, quality, wave, 10K,
rolling, backend, tile, mask-form, setting, concurrency, or scheduler arm.

This continuation is priority `7520`, profile `execution`, under the existing
cumulative `$6` authority. Reuse the retained H200 and its `19:00Z` watchdog,
stop the ring-stack server before mutation, use one durable outer owner plus
the shared repair handshake, and release by `18:50Z`.

The reservation became durable only at `18:34Z`. Director lifecycle file
`DIRECTOR_2000_LIFECYCLE.json` therefore supersedes only those timing fields:
the verified watchdog now runs through `20:00Z`, and the project must release
by `19:50Z`. The scientific scope, comparator, gates, and cumulative `$6`
authority are unchanged.

`DIRECTOR_EXECUTION_CLARIFICATION.json` resolves the execution ownership:
there is intentionally no pre-supplied production-branch runner. The
researcher implements the narrow adapter from the bound sources,
`component_benchmark.py`, and `candidate_endpoint_once.py`. The outer owner
must be detached on the controller host with `unit_manager: pid` and may run
SSH; a guest worker is `remote-shell`. Runner discovery is not a terminal or
return boundary. Launch the durable owner and progress to a real compile or
consumer result under the existing scientific contract.

## Director routing — deep production-branch localization

Three consecutive execution continuations produced no runner, claim, durable
owner, artifact, or typed compile/consumer terminal. The last turn committed
to implementing the runner and then returned unable after 11.581 seconds
without inspecting the branch. This is a model-routing boundary, not evidence
against QLEN.

Priority `7530` routes the same continuation to `deep`. The next result now
requires mechanism-level reasoning across the bound normal two-stage source
dispatch, the first real c32/Q12 prefix/suffix and mask-indptr geometry,
page-1 E5M2 KV ownership, and the H200 production consumer. Inspect only those
bound sources and the two seed scripts, implement the captured-call runner
in-project, and launch the controller-host PID-managed outer owner. Preserve
the cumulative `$6` authority, `19:50Z` release, persisted comparator, exact
component gate, and conditional candidate endpoint unchanged. Do not create a
new project, replay evidence, or treat another readiness-only return as a
terminal.

## Director continuation — corrected real-call component

The deep runner implementation exposed a CUDA-graph observer boundary, not a
QLEN result. Its exact/positive row had mask stride `13` and one KV index per
request, so it represented setup dummy geometry rather than the admitted
approximately 4,214-token c32/Q12 call. Preserve it as an invalid attempt;
neither the scientific component nor endpoint was consumed.

The corrected `FROZEN_PACKET.production-two-stage.tar` is bound at SHA-256
`80a0a8b3878a10c600ba48678dd091f25758385389b148caf5c022bb1b5ae0ce`.
It rejects mask strides below `4000` and disables CUDA graph only for the
component trigger; the conditional endpoint preserves the exact stock launch.
A one-time director inspection found no live remote owner, container, or GPU
process and returned the H200 from maintenance to available.

Priority `7540` changes the profile to `execution` because source localization
is complete. Claim with a fresh controller-host PID-managed owner and fresh
glmrunner-owned remote/local artifact roots. Run the corrected real-call
component once, then only conditionally the candidate endpoint against
persisted `0.6049806232813353 s/request`. Preserve cumulative `$6` authority,
the 19:50Z release, and the verified 20:00Z watchdog. Every diagnostic,
repair, and terminal retrieval must use shared
`research/factory/tools/artifact-snapshot` so repeated snapshots are
content-addressed and immutable rather than extracted into one reused
directory.
