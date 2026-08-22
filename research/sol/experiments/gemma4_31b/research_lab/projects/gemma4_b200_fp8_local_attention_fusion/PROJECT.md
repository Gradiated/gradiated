# B200 local-attention computation fusion

## Question

Can one exact semantics-preserving change inside Gemma 4's recurring
window-1024 local-attention computation remove production launches or
intermediate traffic that the rejected external page-table compaction could
not remove?

## Evidence and scope

Use `$researcher` with the deep profile and `$kernel-research`. Read
`../gemma4_b200_fp8_hybrid_attention_dataflow/B200_FP8_LOCAL_WINDOW_KV_DISCRIMINATOR.json`
once and only the relevant pinned vLLM/FlashInfer source. Preserve the exact
model revision, c32/4214/358 workload, 50 local layers, d256 heads, HND BF16
paged KV, 16-token blocks, 64–65 visible pages, and 17,900 local-attention
calls.

Follow production inputs through the first local-attention consumer and
identify one internal computation or fusion boundary that removes real work,
not an external metadata-copy launch. Produce non-overlapping launch/byte
accounting and either one hash-bound production-input-to-first-consumer
implementation with a correctness oracle and predicted SM100 counter change,
or a typed mechanism rejection.

Do not claim a bench, run CUDA, replay external page compaction, modify the
global K=V candidate or M32 dispatcher, replay an endpoint, or perform provider
operations.

## Artifact and budgets

Write `B200_FP8_LOCAL_ATTENTION_FUSION_DISCRIMINATOR.json`.

- GPU/provider spend: `$0`
- Wall clock: `90 minutes`
- Storage: `1 GiB`
- Endpoint requests: `0`
