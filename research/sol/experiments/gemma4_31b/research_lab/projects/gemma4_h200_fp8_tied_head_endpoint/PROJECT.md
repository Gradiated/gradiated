# FP8 tied vocabulary-head endpoint

## Question

Does a production-bound E4M3 tied output-head consumer reduce exact H200 service time while preserving the model's BF16 embedding, BF16 logits output contract, sampling semantics, and the qualified ring stack?

This is a representation and actual-consumer experiment. Use `$kernel-research`.

## Evidence and physical hypothesis

The exact head is `M<=32, K=5,376, N=262,144`. Historical H200 execution of `torch._scaled_mm` at `M=12` passed the representation and kernel numerical oracles and reduced median kernel time from `0.680032` to `0.360256 ms`. Current-stack evidence attributes only about `0.01087 s/request` to the BF16 head, so this is an incremental stacking opportunity, not a campaign-closing mechanism.

The hypothesis is that retaining a BF16 embedding while holding a separate per-tensor E4M3 output weight halves compulsory head-weight bytes and uses Hopper FP8 tensor-core execution. The predicted discriminator is lower head DRAM traffic and warm latency without changing logits softcap, sampling, token IDs, or any attention/MLP path.

## Frozen scope

- Exact checkpoint and SGLang v0.5.13 image bound in `DIRECTOR_BINDING.json`.
- Target: H200 bench `h200-sync-linear-e00vhh6h29fj68x91g`.
- Decode/prefill output-head shapes only: `M=1, 12, 32`, `K=5,376`, `N=262,144`.
- Candidate: per-tensor E4M3 weight and source-compatible FP8 activation scaling, BF16 accumulation/output as supported by the selected library consumer.
- BF16 tied embedding remains unchanged. No quantized embedding lookup.
- Preserve logits softcap, sampling, CUDA graphs, exact E5M2 ring, QKV, metadata, host gates, runtime flags, and workload.
- Strongest baseline: current BF16 `ParallelLMHead`/logits-processor path on the qualified ring stack.

Do not tune tiles/scales, quantize another projection, change vocabulary, materialize dequantized weights, or sweep formats. Prefer the pinned runtime/library implementation; a custom kernel is permitted only if the real source path cannot invoke the already-supported exact operation.

## Immediate experiment

1. Verify the binding before paid work and inspect the pinned output-head/logits call site.
2. Run one exact producer-consumer component at `M=1,12,32`, including real hidden-state rows. Report BF16/candidate warm distributions, representation error, saturation/nonfinite counts, cosine/relative L2, logits-softcap outputs, and argmax/top-k agreement.
3. Require actual runtime path proof, BF16 embedding preservation, CUDA-graph compatibility, finite logits, and the cheap semantic smoke.
4. If the complete component has any credible positive whole-request bound, run one exact c32 candidate against the persisted qualified ring endpoint. Retain a reproducible positive gain without a fixed percentage threshold.

No positive result is production-qualified until the campaign quality suite covers the final stacked representation.

## Director reactivation — graph-boundary integration

The first exact component is retained without replay. It consumed real hidden-state rows through `LogitsProcessor._compute_lm_head`, preserved the BF16 tied embedding and BF16 logits contract, passed the numerical gates, and reduced the `M=32` median from `0.714848` to `0.415568 ms`. Its endpoint was not started because `graph_capture_seen=false`.

Source inspection localizes that miss: the pinned CUDA graph covers `model.forward`, while logits processing and sampling consume the graph output afterward. Requiring `_compute_lm_head` itself to observe stream capture is therefore not a valid compatibility test. Keep the same representation and actual consumer, but replace only that gate with a runtime path discriminator that proves:

- the pinned model-body CUDA graph is captured and replayed for the exact request;
- the E4M3 head consumes those replay outputs at the observed `M<=32` shapes;
- the original BF16 head compute does not serve candidate requests;
- the BF16 embedding remains unchanged; and
- logits softcap, greedy sampling, token IDs, graph padding, and the qualified ring stack remain intact.

After this path proof, run the cheap semantic smoke and the one previously unstarted exact c32 endpoint against `0.6556567115001144 s/request`. Preserve `artifacts/FINAL_TERMINAL.json` and all prior attempts byte-for-byte; write this continuation to a new iteration root. Do not replay the component, change scale granularity or format, tune a kernel, quantize the embedding, or credit the isolated bound without endpoint evidence.

## Budgets

- Authorized spend: `$10`.
- Compute: one retained H200, at most two claimed GPU-hours.
- Wall deadline: `2026-07-23T23:30:00Z`.
- Storage: at most 8 GiB; no checkpoint duplication.
- Claim the currently available retained H200 after the renewed reservation is durable.
- Provider mutation is forbidden to the researcher.

## Director reactivation — use the graph topology actually measured

The continuation falsified the assumed post-replay boundary, but it also proved the
candidate is already inside the pinned CUDA graph. `model.forward` captured the
E4M3 head at `M=1,2,4,8,12,16,24,32`, replay returned the captured
`LogitsProcessorOutput`, BF16 head fallback remained zero, and the semantic smoke
passed. The missing post-graph Python event was therefore an impossible validator,
not an integration failure.

Preserve the settled real-row component and every prior iteration. In a new
iteration, require the bound topology decision to rehash, prove the E4M3 head is
present in each required graph capture and that candidate requests replay those
graphs, retain zero BF16 fallback plus the BF16 embedding and logits/sampling
contracts, and run the one previously unstarted exact c32 endpoint against
`0.6556567115001144 s/request`. Do not require a post-replay head call, replay the
component, change the representation, tune a kernel, or move the head outside
`model.forward`.

The endpoint must complete 32/32 finite rows with exactly 358 output tokens each,
`17,120` cached and `117,728` fresh prompt tokens, and the existing path and
semantic gates. A positive result is retained as an incremental candidate but
does not make a campaign quality claim.
