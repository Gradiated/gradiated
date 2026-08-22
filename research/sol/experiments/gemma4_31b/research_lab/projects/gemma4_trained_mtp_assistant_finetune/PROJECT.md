# Trained Gemma 4 MTP assistant

## Question

Can a short, workload-aware fine-tune of Google's existing Gemma 4 31B
assistant increase useful accepted draft work enough to reduce the exact c32
endpoint cost relative to both autoregressive serving and the unchanged
assistant checkpoint?

## Why this is worth testing

The official assistant is a four-layer, hidden-size-1024 model of about 470M
parameters. It shares target KV state and is materially smaller than the 31B
verifier. The prior SGLang DFlash/MTP work proved that the exact target enters
the assistant path and measured roughly 3.006 accepted target tokens per
depth-4 verification, but only a 1.135% endpoint improvement. That closes the
old checkpoint/runtime combination, not a workload-tuned assistant on vLLM's
current native Gemma 4 MTP implementation.

Current upstream vLLM maps `gemma4_assistant` checkpoints to its native
`Gemma4MTPModel`, and Speculators provides online hidden-state extraction and
MTP fine-tuning. Fine-tuning an existing small assistant is a cheaper and
better-founded test than another untrained linear offset head.

## Bound identities

- Target: `google/gemma-4-31B-it` at
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Starting assistant: `google/gemma-4-31B-it-assistant` at
  `627c5ec1458b9086b841a91e0512fd31fd2fbbf1`.
- Existing assistant bytes:
  `../sglang_v0512_h200_gemma4_mtp_endpoint/artifacts/assistant`, with
  `model.safetensors` SHA-256
  `9f80df6099fa1fd7db71220ec9ee864d5ecff769878697dd5763e4285b15a1da`.
- Exact endpoint workload: 32 concurrent requests, 4,214 prompt tokens and
  358 output tokens per request. Reuse the content-addressed c32 payloads with
  request identity
  `60630a80335d5a95ebae87dd2d852c6cb8749a0b92e8617261ec6750b64a794c`.
- Runtime starting point: official vLLM `0.26.0+cu129`; pin the exact wheel or
  source identity before the first scientific run.
- Prior evidence:
  `../gemma4_lossless_parallel_draft_frontier/PARALLEL_DRAFT_FRONTIER.json`
  and
  `../gemma4_causal_parallel_offset_head/CAUSAL_PARALLEL_OFFSET_HEAD_RESULT.json`.

## Experiment

Use `$researcher` and `$experiment-run`.

1. Reuse Speculators' supported online-training path. Do not build a new
   trainer unless one narrow Gemma adapter is actually missing.
2. Use two independent 1x H200 benches: one frozen target server for
   target-generated responses/hidden states and one trainer. Preserve the
   target checkpoint and generated dataset across repairs.
3. Fine-tune the existing assistant for one bounded pilot on 5,000
   target-generated examples. Use a request-disjoint 512-example holdout.
   Draw prompts from broad instruction, reasoning, code, and tool-use sources;
   do not train on GPQA-Diamond or TauBench evaluation items.
4. Measure the unchanged assistant and fine-tuned assistant on the same
   holdout at draft depths 4 and 6. Record accepted-prefix distributions,
   assistant CUDA time, target-verification CUDA time, and accepted target
   tokens per combined CUDA second.
5. If the trained checkpoint improves the holdout efficiency metric and has a
   positive whole-request bound, run one same-session c32 comparison:
   autoregressive control, unchanged assistant, and fine-tuned assistant.
   Keep the exact target verifier, request set, sampling, cache accounting,
   target runtime, and hardware unchanged.

The assistant may propose tokens but never decides output. The unchanged
target verifier remains the sole acceptance authority, so the mechanism is
lossless with respect to the target distribution when the runtime's
speculative sampler contract passes.

If the current Speculators MTP trainer cannot load the separate Gemma
assistant after one localized adapter attempt, preserve that evidence and
warm-start its confirmed Gemma 4 EAGLE-3 training path from
`RedHatAI/gemma-4-31B-it-speculator.eagle3`. Do not spend the session
rebuilding training infrastructure or return to the already-falsified linear
offset head.

## Gates and stop rules

- Correctness: stock and trained speculation must use target verification,
  complete all requests, produce finite outputs, and pass the runtime's
  probability-preservation/greedy-equivalence contract as applicable.
- Training: require decreasing held-out loss or increasing accepted-target
  tokens per combined draft-plus-verify CUDA second. Stop after the first
  bounded pilot if neither moves.
- Performance: a small positive endpoint result is retained; do not impose an
  arbitrary per-experiment percentage gate. Do not claim the campaign's 20%
  objective without a matched endpoint and price-normalized result.
- Scope: broad quality evaluation is deferred because target verification
  preserves output. GPQA-Diamond and TauBench remain later product gates.
- Budget: at most $20 cumulative provider exposure, including both H200s,
  storage, setup, training, endpoint evaluation, and cleanup margin.
- Timeout: 4.5 hours from provider creation, with independent absolute
  watchdogs and verified cleanup. Keep a useful bench only when the next arm
  can start inside ten minutes.

## Required artifacts

- `EXPERIMENT_CONTRACT.json` plus pinned software/data identities.
- Phase timestamps and provider-active versus useful-GPU seconds.
- Target-generated train/holdout manifests without evaluation contamination.
- Stock and trained assistant checkpoint manifests.
- Training curves and holdout accepted-prefix/CUDA distributions.
- Same-session endpoint artifacts if the holdout promotes.
- A typed terminal naming the residual bottleneck and the next trained
  speculation change, even when the result is negative.
