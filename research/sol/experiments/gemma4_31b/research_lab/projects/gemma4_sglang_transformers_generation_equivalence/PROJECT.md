# Gemma 4 SGLang versus Transformers generation equivalence

## Question

Is the frozen `heldout_ordering` quality failure intrinsic to the exact Gemma 4 31B checkpoint under the admitted safe-code request, or does SGLang v0.5.12 diverge from direct Transformers greedy generation despite identical prompt-token identity?

## Why this matters

SGLang on H200 is the campaign's only complete-request economic pass: 32/32 exact 4,214/358 requests at `0.3633031778 s/request`, below the strict `0.4720118230` ceiling. Production eligibility is blocked because both SGLang BF16-KV and FP8-E5M2-KV failed the same held-out ordering task. The existing direct Transformers sentinel proves 240-token prompt identity and matched NLL, but it did not generate or score a direct-reference answer. A direct greedy-generation discriminator can distinguish a checkpoint/prompt limitation from a runtime decode defect without reopening prompt engineering, adapters, FP8, or concurrency.

## Experiment

Use the exact checkpoint, tokenizer, immutable linux/amd64 SGLang image, safe-code transformer, adapter, and strict scorer bound in `BINDINGS.json`. Freeze exact input token IDs once and feed those bytes to both consumers:

1. Direct Transformers BF16 greedy generation (`do_sample=false`) in the bound image.
2. SGLang v0.5.12 BF16-weight/BF16-KV greedy generation through its native token-ID path, with identical maximum output length and stop-token IDs.

Run `heldout_ordering` first, followed by the original `python` case and the three passing held-out code controls (`heldout_aggregation`, `heldout_indexing`, `heldout_branching`). Persist raw requests, token IDs, output token IDs/text, finish reasons, per-case strict scores, and the first token/logit divergence when available. Mechanically reject any prompt, template, policy, adapter, checkpoint, or scorer drift before provider creation.

## Decision contract

- If direct Transformers and SGLang both fail `heldout_ordering`, close this model/prompt quality branch; no further prompt, adapter, c64, or seal-only successor is admitted.
- If direct Transformers passes and SGLang fails under byte-identical input IDs, preserve the bench and continue in this same project with `researcher_profile: deep` to locate the first generation divergence across sampling, stop handling, logits processing, and pinned runtime source.
- If both pass, treat the prior quality capture as a request-path discrepancy and isolate it in this project using the preserved raw bytes; do not claim eligibility from the new row alone.
- No FP8, performance sweep, concurrency arm, prompt mutation, policy relaxation, or quality claim outside these five frozen cases is allowed.

## Resources and limits

- Execution profile; director-owned preemptible `nvidia-h200-sxm` bench with one 250-GiB disk.
- Provider create is gated on one typed local identity/runner terminal and remains director-only.
- 90 wall minutes, 70 H200 provider minutes, 1.1667 H200-hours, and `$3.25` project spend.
- Use a mutable retained bench and actual retryable calls for transfer, image/runtime setup, each consumer, and artifact retrieval. Release without teardown; the director owns reuse or cleanup.
- Local preparation: 30 wall minutes, 2 CPU-hours, 2 GiB working storage, and no provider spend.

## Required terminal

A content-addressed JSON terminal containing exact identities, raw artifact hashes, prompt/output token-ID equality or first divergence, strict scores for both consumers, the typed branch decision, provider exposure, and bench release state.
