# Static c32 multi-token background decode engine

## Question

Can a background-only fixed-c32 executor reduce the qualified Gemma 4 request cost by keeping eight greedy decode steps on device between host boundaries, while producing the exact 358 token IDs required by the bound workload?

This is a serving-topology and accelerator-dataflow experiment. Use `$kernel-research`.

## Evidence and physical hypothesis

The qualified comparator is `0.6556567115001144 s/request` with 32/32 complete requests, 4,214 prompt tokens, exactly 358 completion tokens, temperature zero, `min_tokens=max_tokens=358`, `ignore_eos=true`, and exact `17,120` cached plus `117,728` fresh prompt-token accounting.

The scope-matched residual profile assigns `8.375068794 s` or `52.5196%` of decode wall time to synchronization and another `0.766971497 s` or `4.8096%` to scheduler gaps. The prior device-conditional graph proved that four model graphs replay correctly, but also proved that stock SGLang returns to host sampling, result processing, decode preparation, and running-batch mutation after every token. That closes graphing the unchanged serving body; it does not test a fixed background executor that removes those host-owned semantics from the inner loop.

The physical hypothesis is that the exact campaign workload permits a fixed 32-row decode batch with no early exit. An eight-token unrolled CUDA graph can keep logits softcap, greedy argmax, next-token IDs, positions, sequence lengths, and KV writes on device, exposing the host only at eight-token block boundaries. The predicted discriminator is eight model forwards per host boundary with identical token IDs and fewer host synchronizations, scheduler transitions, and graph launches per generated token.

## Frozen scope

- Exact checkpoint `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Pinned SGLang v0.5.13 image `docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- H200 bench `h200-sync-linear-e00vhh6h29fj68x91g`.
- Qualified exact E5M2 ring stack and comparator bound in `DIRECTOR_BINDING.json`.
- Fixed c32 workload: 4,214 prompt tokens, 358 completion tokens, 535-token shared prefix, temperature zero, fixed seed, forced length, and streaming only at block boundaries.
- Candidate: exactly eight greedy decode steps per device-resident block, plus the fixed six-token tail. No block-length sweep.
- Preserve every checkpoint weight, FP8 linear, QKV, attention, ring, cache, logits-softcap, and token-selection value.

This is a background-agent serving mode. It may trade token streaming cadence and TTFT for cost, but must preserve final ordered token IDs, completion length, request isolation, and bounded completion time. It is distinct from the closed device-conditional serving-body experiment: do not replay that candidate, the negative host continuous-step flag, or scheduler-stream snapshot.

## Immediate experiment

1. Rehash the immutable binding and source-bind the pinned model runner, CUDA-graph replay, logits softcap, greedy sampler, KV positions, and batch metadata.
2. Build one fixed-c32 eight-token inner loop below the host scheduler. The first tiny H200 invocation is the discovery audit; repair ordinary API, graph, or layout defects in the retained claim.
3. Run one exact component on captured real state. Require bit-exact token IDs for at least two eight-token blocks and the six-token tail, exact KV/position transitions, graph padding invariants, finite outputs, and measured reductions in host synchronization and scheduler transitions per token.
4. If the component passes, one untimed stock c32 capture is allowed solely to freeze all 32×358 control token IDs; it is not a timing comparator and may not replay any historical performance arm.
5. If the complete component has a credible positive whole-request bound, run exactly one c32 candidate against the persisted qualified timing comparator. Require 32/32 rows, exactly 358 output tokens each, exact cache accounting, final token-ID equality against the fresh frozen control capture, and report service time, throughput, power, utilization, and block-streaming latency.

No broad endpoint framework, dynamic-batch implementation, block-size sweep, sampling-mode expansion, or quality claim is authorized. A positive result establishes a workload-scoped background serving candidate; general OpenRouter feature support remains a later gate.

## Budgets

- Authorized spend: `$16`.
- Compute: one retained H200, at most three claimed GPU-hours.
- Wall deadline: `2026-07-24T01:15:00Z`.
- Storage: at most 12 GiB; no checkpoint duplication.
- Prepare offline behind the priority-4500 tied-head endpoint and claim the shared bench only after it releases.
- Provider mutation is forbidden to the researcher.

## Director reactivation — capture the dependency chain once

The first candidate established the physical opportunity but consumed its exact
direct-replay mechanism. It reduced host result boundaries from 21 to 3, preserved
the recorded position and KV-slot transitions, and projected
`0.6286271699 s/request`; however, repeatedly launching one captured single-token
graph without a host result boundary produced nonfinite outputs and only 72/704
matching token IDs. No endpoint ran.

Use `$kernel-research` for one materially different implementation: capture an
ordered eight-step supergraph in which greedy token selection, the next token
input, positions, sequence lengths, and pre-reserved KV locations are explicit
device tensors connected between the eight model forwards. Use fixed ping-pong
state buffers or an equivalently explicit lifetime discipline so each step
consumes the immediately preceding finite token result. Launch the whole
eight-step graph once per block, with a separately captured six-step tail. Do not
replay or repair the consumed repeated-single-step candidate.

The component must compare the new supergraph with a fresh untimed stock token
oracle on the same captured real state. Require 704/704 exact token IDs, 32/32
exact rows, finite logits/results at every transition, byte-exact KV writes,
exact positions and request ownership, and 3 rather than 21 host boundaries.
Measure graph instantiation memory, replay wall time, launch count, host
synchronizations, and the conservative whole-request bound. Run one exact c32
endpoint only if this complete component is semantically exact and credibly
positive. Preserve the bound checkpoint, image, E5M2 ring, workload, comparator,
block geometry, and accounting; allow no block sweep, speculative tokens, model
change, tied-head stack, or closed continuous-step/conditional-body replay.
