# Tied vocabulary projection cost bound

## Decision question

Can any isolated change to Gemma 4 31B's tied `262144 x 5376` embedding/output matrix plausibly clear the campaign's 5% whole-request cost relevance threshold or create a necessary L40S capacity discontinuity, before paying for quality or CUDA work?

This is a `$0` analytical falsifier for a materially different model-change mechanism. It cannot alter the live/corrective paid project, download weights, claim quality, or nominate an endpoint based on FLOPs alone.

## Why now

The exact model has an unusually large vocabulary and tied embedding/output weights. The paid lane measures its actual retained-BF16 `m=1` projection alongside FP8 decoder shapes, but the maximum mechanism value can already be bounded from exact geometry, workload mix, weight residency, and required logits. A quick bound prevents a visually large tensor from becoming an unjustified paid or quality project.

## Authoritative inputs

- `../../CAMPAIGN.md`
- `../exact_geometry_runtime_opportunities/GEOMETRY.json`
- `../fp8_l40s_fit_economic_falsifier/MEMORY_ACCOUNTING.json`
- `../l40s_saturation_economic_gate/SATURATION_GATE.json`
- `../gemma_l40s_fp8_exact_shape_microbench/artifacts/preflight-20260717T001000Z.json`

Use the exact model revision, 4,214/358 workload, 10K comparator, and L40S envelope. Do not inspect, wait for, or modify any provider owner.

## Immediate experiment

1. Reconstruct exact tied-matrix parameters, BF16/FP8/INT8 bytes, logits FLOPs, embedding-lookup bytes, and any duplicate-storage requirement when input embeddings and output weights use different representations.
2. Bound whole-request saved bytes and FLOPs for: output-only FP8/INT8 storage, a hypothetical perfect vocabulary shortlist, and reduced-vocabulary proxy sizes. Keep prompt embedding lookup, decoder layers, sampling/softmax, and required full-vocabulary correctness explicit. Report impossible perfect-elimination bounds as ceilings, not proposals.
3. Test whether any admissible isolated representation clears 5% under conservative prompt/decode denominators or changes c4/c8/10K L40S fit. Do not convert arithmetic ratios into endpoint throughput.
4. Record support and quality constraints caused by tied weights, tokenizer coverage, rare-token behavior, multilingual/code/tool tokens, logprobs, and exact OpenAI-compatible output semantics.

Nominate at most one later candidate only if it has a conservative >=5% mechanism or a necessary capacity discontinuity and a credible consumer path. Otherwise close this line. Paid microbenchmark timings may later sharpen the bound, but this project must finish without waiting for them.

## Artifacts and budgets

- Terminal artifacts: `VOCAB_BOUND.json` and `DECISION.md`.
- Wall clock: 30 minutes.
- Compute: at most 1 local CPU-hour; no CUDA.
- Storage: at most 128 MiB.
- Provider mutation and spend: prohibited; `$0`.

