# Fused E4M3 tied-head greedy top-1

## Question

Can the exact forced-greedy c32 workload avoid materializing and rescanning the
full `M x 262,144` BF16 logits tensor by reducing the validated E4M3 tied-head
GEMM directly to one token per row, while preserving every selected token and
the measured tied-head endpoint gain?

Use `$kernel-research`.

## Evidence and physical hypothesis

The predecessor's real `LogitsProcessor._compute_lm_head` consumer has
`M in {1,2,4,8,12,16,24,32}`, `K=5,376`, and `N=262,144`. Its validated E4M3
path preserves the BF16 embedding, emits BF16 logits, has zero BF16-head
fallback, and reduced the `M=32` head median from `0.714848` to `0.415568 ms`.
The exact endpoint completed 32/32 at `0.6518282820 s/request`, 0.5839% below
the qualified ring comparator, with passing smoke and exact token accounting.

That path still writes the entire BF16 vocabulary tensor, applies the monotonic
Gemma logits softcap of 30, and scans it for greedy sampling even though the
bound workload requests no logprobs and uses temperature zero. A tiled E4M3
GEMM whose CTA epilogue emits only finite per-row partial `(value,index)` pairs,
followed by one deterministic device reduction, can remove the full-logits
write, softcap pass, and sampler scan. Because the softcap is monotonic, the
selected index is the required semantic discriminator; ties must use the stock
lowest-index rule.

## Frozen scope

- Exact checkpoint `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Pinned SGLang v0.5.13 image
  `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Retained H200 `h200-sync-linear-e00vhh6h29fj68x91g`.
- Predecessor E4M3 tied-head weights/scales, BF16 hidden states and embedding,
  exact graph padding shapes, qualified ring stack, and exact c32 workload.
- Candidate output is exactly one greedy token ID per live row. It is valid
  only for temperature-zero requests with no requested logprobs; all other
  sampling and logprob modes must use the unchanged full-logits path.

No format, scale, tile, split, vocabulary, concurrency, or sampling sweep is
authorized. Do not replay the predecessor component or endpoint, change the
embedding, stack the quality-unsafe width proxy, or claim general feature or
model quality.

## Immediate experiment

1. Source-bind the exact E4M3 head, logits softcap, sampler, captured padded
   shapes, and fallback boundary from `DIRECTOR_BINDING.json`.
2. Implement one H200 E4M3 head-to-token consumer. Use the best single fixed
   CTA/cluster decomposition for these shapes, emit only deterministic partial
   top-1 values and indices, and reduce them on device. Preserve graph capture
   and replay for every required padded `M`.
3. Measure one actual-consumer component on predecessor-captured real hidden
   rows for every `M in {1,2,4,8,12,16,24,32}`. Compare against the existing
   E4M3 full-logits plus softcap plus greedy-sampler path. Require identical
   token IDs for every row and repeat, finite partial/final values, correct
   lowest-index tie behavior, zero BF16 fallback, graph capture/replay, and a
   positive measured full-consumer bound.
4. Only if the complete component is exact and credibly positive, run one exact
   c32 endpoint against the persisted `0.6518282819688466 s/request` tied-head
   result. Require 32/32 finite nonempty rows, 358 completion tokens each, exact
   `17,120` cached plus `117,728` fresh prompt-token accounting, unchanged smoke,
   and explicit fallback proof for an out-of-scope non-greedy probe.

## Budgets

- Authorized spend: `$10`.
- Compute: one retained H200, at most two claimed GPU-hours.
- Wall deadline: `2026-07-24T01:20:00Z`.
- Storage: at most 8 GiB; no checkpoint duplication.
- Prepare offline behind priority-4900 and share the retained bench
  sequentially.
- Provider mutation is forbidden to the researcher.
