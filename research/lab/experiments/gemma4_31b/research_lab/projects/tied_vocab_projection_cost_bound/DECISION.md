# Decision — close tied-vocabulary cost-bound line

The exact metadata bound closes this `$0` line with no nominee. The tied matrix
is `262,144 x 5,376 = 1,409,286,144` parameters: **2.625 GiB in BF16** or
**1.3125 GiB at one byte/parameter**, and each full-vocabulary logits position
is **2,818,572,288 FLOPs**.

For the primary `4,214 prompt / 358 output` request, one final-prefill logits
position plus 358 decode positions makes the entire tied projection only
**0.3750%** of the decoder-plus-required-full-vocabulary-logits FLOP
denominator. At the 10K-input comparator it is **0.1659%**. Even an
impossible perfect shortlist therefore cannot approach the campaign's 5%
whole-request relevance threshold; 131K, 65K, 32K, 16K, 8K, and 4K row
proxies save only 0.1875%, 0.2813%, 0.3281%, 0.3516%, 0.3633%, and 0.3692%
respectively on the primary slice. These are arithmetic ceilings, not
throughput or endpoint-cost results.

An output-only FP8/INT8 representation cannot share the tied storage with the
BF16 input embedding. Duplicating the one-byte output matrix adds 1.3125 GiB,
making the conservative primary c8 total **46.3585 GiB** against the
**44.704 GiB** L40S envelope. Jointly converting both input and output could
lower that total to **43.7335 GiB**, but it changes prompt embedding numerics,
requires a new quantized embedding/output consumer, and is excluded by the
pinned runtime's execution-equivalent path. A perfect shortlist also violates
full-vocabulary correctness, tokenizer coverage, logprobs/sampling, rare and
multilingual/code/tool tokens, and exact OpenAI-compatible output semantics.

Conclusion: no isolated representation or shortlist change has a credible
consumer plus a conservative 5% mechanism or necessary capacity discontinuity.
Do not create a paid arm or wait for the paid owner. `VOCAB_BOUND.json` and
`run_bound.py` contain the reproducible formulas, hashes, and raw derived
values. No CUDA, provider, quality, or endpoint measurement was performed.
