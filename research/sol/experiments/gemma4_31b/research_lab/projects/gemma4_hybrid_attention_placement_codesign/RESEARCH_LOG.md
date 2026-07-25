# Research log

## 2026-07-25 — source-complete 55-local/5-global candidate

Question: can changing the pinned 60-layer 5-local/1-global geometry produce a
material H200 c32 gain with a credible recovery path?

Action: verified the three director-bound hashes, the exact M384 trace, the
scope-matched prefill subtype map, the prefill profile, and the four-row NCU
export. `simulate_placements.py` reconstructs all 60 layers. For verification
it maps 15 exact c32 target cycles into each layer's QKV, attention, output,
gate/up, and down cost. For prefill it combines measured local/global attention
subtype time with measured aggregate FP8-linear time apportioned by exact
projection FLOPs. It also computes exact causal/windowed attention pairs, FP8
KV bytes, projection parameters, and two counter-derived full-request pass
counts.

Evidence: stock M384 attention is `1.339264 ms` per local layer and
`3.275520 ms` per global layer; the valid mixed component is `0.936512 ms`
local and `3.274080 ms` global. The trace-derived attention projection medians
are `0.138144 ms` local and `0.211249 ms` global. Scope-matched prefill
attention is `34.671859 ms` per local layer and `150.025741 ms` per global
layer per c32 batch. Placement-only movement with ten global layers has zero
modeled cost effect.

Result: retain one quality-unsafe candidate with full layers
`[5,17,29,41,53]`. Replacing the other five global layers predicts
`12.053363 ms` less target-cycle work, `31.526–33.291 ms/request` total
savings, and `0.591858–0.593624 s/request` against the locked
`0.625149102` denominator: `5.043–5.325%`. It removes `330,301,440`
attention-linear parameters and `1,419,509,760` c32 KV bytes (`7.493%`).
Measured NCU geometry per converted layer moves from 255 to 173
registers/thread, 102.4 to 37.888 KiB dynamic shared memory, 7.76 to 15.52
waves/SM, 1.351311 to 0.662617 GB DRAM reads, and 6.713353 to 1.554938 GB L2
bytes. No batching gain is credited because prior c48/c64 results were
negative.

Interpretation: this is a source-complete performance candidate, not a
deployable model or a measured endpoint. The M8 endpoint consumer produced no
durable pair, and prefill linear time is a FLOP-calibrated allocation rather
than a per-shape timing. The cheapest later proxy copies nearest-local
attention weights into the five converted modules, keeps MLP/norm weights,
and measures one exact c32 target-forward comparison before any endpoint.
Recovery requires teacher hidden-state/attention/logit distillation on
long-context and tool-use data, then exact GPQA-Diamond, TauBench,
long-context, tool-format, and multimodal gates.

One initial local invocation was invalid only because the NCU CSV units row
was parsed as a sample. The consumer now filters nonnumeric IDs; the same
deterministic simulation completed without changing the scientific question.
`python3 -m unittest -v test_simulate_placements.py` passes both binding and
combinatoric tests. No GPU was claimed and provider spend is `$0`.
