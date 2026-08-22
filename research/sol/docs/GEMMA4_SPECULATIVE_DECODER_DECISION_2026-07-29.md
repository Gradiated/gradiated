# Gemma 4 speculative decoder decision

Date: 2026-07-29

## Decision

Lossless speculative decoding is one of the most credible routes from the
current measured B200 dynamic-FP8 c64 result (`0.584284801 s/request`) to the
campaign target (`0.500119281574996 s/request`). The required improvement is
only `1.168291x`, or a `14.404879%` reduction in service time.

Do not begin by training a new standalone autoregressive student. First run the
current public Gemma 4 31B drafts through the current production runtime:

1. `z-lab/gemma-4-31B-it-DFlash`, a 2B, five-layer, block-16 parallel draft;
2. `RedHatAI/gemma-4-31B-it-speculator.eagle3`, a one-layer feature drafter;
3. `google/gemma-4-31B-it-assistant`, through vLLM's Gemma 4 MTP path.

If none clears the B200 c64 wall-time gate, train or fine-tune a
Gemma-specific **one-forward parallel drafter** on the campaign's on-policy
Gemma outputs. Prefer DFlash, P-EAGLE, or a semi-autoregressive parallel design
over a conventional small autoregressive decoder because saturated throughput,
not single-request latency, is the objective.

The target model remains frozen. Correct speculative verification preserves
the target sampling distribution, so draft training changes acceptance and
cost rather than model quality. Exact target-token, acceptance, and KV-commit
semantics remain implementation gates.

## Evidence and reconciliation with the lab's prior result

### Measured local evidence

- The qualified H200 baseline is `0.625149101968745 s/request`; its 20% target
  is `0.500119281574996`.
- The newer B200 dynamic-FP8 c64 endpoint is `0.584284801 s/request`, but is not
  yet quality-qualified.
- The retained SGLang DFlash transition diverged before acceptance: ordinary
  target token `3496` versus verifier token `759`.
- Under that old H200 verifier geometry, a charged depth-16 route required
  `16.054` accepted target tokens per verification, while the measured
  depth-four route delivered `3.0063` and only `1.135%` paired endpoint
  improvement.

That result rejects the captured SGLang transition and its cost geometry. It
does not reject a current vLLM implementation, a different verifier kernel, or
parallel drafting generally. The `16.054` hurdle must not be transferred to
the current B200 endpoint without remeasuring `C_draft(k)` and `C_verify(k)`.

### Published and implementation evidence

- Z Lab publishes an exact Gemma 4 31B DFlash draft with 2B BF16 parameters,
  five decoder layers, six target hidden-state inputs, and block size 16. Its
  vendor benchmark on one B300 reports c32 generated-token throughput speedups
  from `1.9x` on MT-Bench to `3.8x` on Math500, with mean accepted lengths from
  `4.19` to `8.62`. These are vendor-reported, different-hardware results, not
  transferable campaign measurements.
- Red Hat publishes a Gemma 4 31B EAGLE-3 checkpoint with one transformer layer
  and target hidden states from layers 2, 30, and 57. Its reported accepted
  length at draft depth five ranges from `2.20` to `3.93` by domain.
- vLLM's current documentation provides a distinct Gemma 4 MTP path for the
  Google assistant checkpoint, including shared target/draft KV handling.
- P-EAGLE reports `1.10x-1.36x` over EAGLE-3 by replacing serial drafting with
  one-forward parallel prediction. That relative range spans the campaign's
  remaining `1.168x` requirement, but it was measured on other models.
- SPEED-Bench shows why the endpoint test must use representative prompts and
  concurrency: synthetic inputs overestimated speculative throughput by 23%
  on average in its experiments, and the optimal draft length shifted with
  batch size.
- DSpark's current design directly addresses the relevant failure mode:
  parallel suffix acceptance decays, while long verification blocks waste
  capacity at high concurrency. It combines a parallel backbone, a lightweight
  sequential module, and confidence/load-aware verification length.

## Minimal experiment sequence

### Phase 1: no training

Use the current B200 runtime and the exact c64 campaign workload. Run one
matched endpoint per public draft, starting with the official DFlash Gemma 4
container/current vLLM path. For each arm record:

- accepted-length distribution by token position, prompt class, and request;
- draft, target-verification, acceptance/KV-commit, and scheduler wall time;
- generated and accepted tokens per GPU-second;
- HBM use, prefix-cache hit rate, effective c64 occupancy, and fallback rate;
- exact greedy target-token/KV transition on a small deterministic oracle;
- whole-request service time and price-normalized `$ / M` total tokens.

Sweep only draft lengths supported by the checkpoint and current telemetry.
For DFlash, test `{4, 8, 12, 16}` only if each predecessor leaves economic
headroom. Select by measured
`expected accepted target tokens / (draft cost + verification cost)`, not by
acceptance alone.

Promote any arm at or below `0.500119281574996 s/request`, or retain a smaller
positive gain if it stacks cleanly with the current B200 FP8 route. A public
draft miss is still useful: it yields the cost and acceptance curves needed to
size training.

### Phase 2: workload adaptation

Fine-tune the strongest public drafter before inventing a new architecture.
Generate responses from the exact pinned Gemma target over production-like
chat/tool traces plus GPQA-Diamond and TauBench-style traffic. Match the
serving context-length and sampling distribution; include multilingual traffic
if the endpoint will accept it. Freeze the target and train only the drafter.

The first training objective is not generic perplexity. It is accepted target
tokens per measured verifier GPU-second at c64. Use per-position acceptance
loss and confidence calibration so the runtime can truncate low-survival
suffixes.

### Phase 3: new parallel drafter only if needed

Build a small Gemma-specific feature drafter that consumes several frozen
target hidden states and predicts a path-conditioned 8-16-token block in one
forward. Start with one to three lightweight transformer layers and a shared
hidden state or semi-autoregressive correction module. Keep the full Gemma
vocabulary initially; vocabulary pruning is a later measured optimization
because it can disproportionately miss multilingual target tokens.

The design goal is a smaller and cheaper draft than the public 2B DFlash model
with enough branch conditioning to avoid suffix acceptance collapse. Its
architecture and draft depth should be chosen from the measured B200
draft/verify roofline, not from a fixed parameter-count target.

## Risks

- At c64 the verifier can become compute-bound; speculative decoding can reduce
  latency while lowering saturated throughput. Only the matched endpoint
  decides this.
- Gemma's heterogeneous local/global attention and multimodal runtime have had
  draft-backend and prefix-cache integration failures. Current vLLM support
  should be tested rather than assuming old SGLang behavior is repaired.
- A public checkpoint may be trained on chat/coding distributions unlike the
  OpenRouter mix. Acceptance must be measured by domain and context length.
- The B200 endpoint is not quality-qualified, so reaching the time target does
  not by itself make a launch claim.

## Sources

- Z Lab Gemma 4 31B DFlash model card and benchmark:
  https://huggingface.co/z-lab/gemma-4-31B-it-DFlash
- DFlash implementation:
  https://github.com/z-lab/dflash
- Red Hat Gemma 4 31B EAGLE-3 checkpoint:
  https://huggingface.co/RedHatAI/gemma-4-31B-it-speculator.eagle3
- vLLM Speculators:
  https://github.com/vllm-project/speculators
- vLLM Gemma 4 MTP documentation:
  https://github.com/vllm-project/vllm/blob/main/docs/features/speculative_decoding/mtp.md
- P-EAGLE:
  https://arxiv.org/abs/2602.01469
- SPEED-Bench:
  https://arxiv.org/abs/2604.09557
- DSpark:
  https://arxiv.org/abs/2607.05147
- Local discriminator:
  `research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_lossless_parallel_draft_discriminator/LOSSLESS_TRANSITION_DISCRIMINATOR_RESULT.json`
