# Tile-aligned 16,384-wide MLP co-design proxy on H200

## Question

Would reducing Gemma 4's 21,504-channel SwiGLU intermediate to one H200-aligned 16,384-channel representation remove enough measured FP8-linear work to justify structured recovery training?

## Why this matters

The qualified stack remains at `0.6743258590 s/request`, above the `0.6381105231` ceiling, and the current profile assigns `24.058943%` of wall time to FP8 linears. Kernel-only gate/up scheduling, W4, static FP8, Stream-K, activation-to-down fusion, and RMSNorm-to-FP8 producer fusion are closed. The latest producer candidate reduced small-shape component time but had only a `0.00580035%` conservative endpoint bound and failed exact numerical equivalence.

This project changes model geometry rather than reopening those schedules. A 16,384-channel intermediate removes `5,120 / 21,504 = 23.8095%` of the gate, up, and down channel work while keeping hidden size 5,376, depth 60, attention, KV, vocabulary head, precision, and serving geometry unchanged. Both 16,384 and the packed 32,768 gate/up width are tensor-tile aligned. The experiment is explicitly a quality-unsafe execution proxy: it can establish a cost floor and nominate one later recovery program, but it cannot become a production frontier.

## Immutable identity and candidate

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: SGLang v0.5.13 commit `28b095c01005d4a3a2a5b637b7d028b07fba31b2`, pinned Linux/amd64 image digest `6113665a…`.
- Workload: c32, 32 requests, 4,214 prompt and 358 completion tokens each, exactly 17,120 cached and 117,728 fresh prompt tokens.
- Control: qualified E5M2 endpoint at `0.6743258590313417 s/request`.
- Original per-layer shapes: hidden 5,376, intermediate 21,504, packed gate/up output 43,008.
- Candidate: exactly 16,384 intermediate channels and packed gate/up output 32,768 in all 60 layers.

For each layer, compute one deterministic calibration-free joint channel score from the original gate, up, and down weight norms, retain the top 16,384 indices, sort those indices into canonical ascending order, and repack the corresponding gate/up output rows, down input columns, and their existing FP8 scale metadata. Freeze this selection rule, tie handling, and seed before GPU science. There is no width, ranking, calibration, or layerwise sweep.

`DIRECTOR_BINDING.json` and `verify_director_binding.py` mechanically bind the stack, current profile, exact control, and measured real-weight geometry.

## Immediate experiment

Use the available retained checkpoint read-only and prepare behind the higher-priority block-paging lane. After the `$12` reservation is durable and that lane releases `h200-sync-linear-e00vhh6h29fj68x91g`, claim it. Materialize only a project-local sparse overlay or load-time repack; do not copy or rewrite the checkpoint.

First measure the actual FP8 consumers at production M=32 and the observed prefill M values for packed gate/up and down, including all outputs and existing scale conventions. Prove the exact candidate shapes, 60-layer route, finite output, and unchanged non-MLP paths. Derive a scope-matched endpoint bound from the current trace rather than multiplying the entire FP8 boundary blindly.

If the measured conservative whole-request reduction is positive, launch exactly one profiler-off c32 candidate against the persisted control. Run three cheap coherence discriminators before timing, but treat their failure as quality evidence rather than a performance falsifier: a finite, mechanically correct candidate may still run the frozen throughput workload as an explicitly unsafe proxy. Require 32/32 completed rows and exact token/cache accounting for a performance result.

## Decision and stop rules

A measured candidate at or below `0.6381105231 s/request` nominates one later structured recovery/distillation project; it does not authorize deployment. A smaller positive result remains model-hardware evidence and should be retained for stacking. Close on load/repack incompatibility after one ordinary repair, non-finite execution, wrong channel/scale routing, a non-positive component bound, invalid accounting, or endpoint regression.

Do not change hidden size, depth, attention, KV, precision, width, selection rule, runtime flags, workload, or add a second candidate. Do not train, distill, broadly evaluate quality, or claim production equivalence in this project.

- Researcher profile: `deep`.
- One retained H200; at most 120 claimed GPU-minutes and 240 wall minutes from first claim.
- Project authorization: `$12.00`.
- At most 24 GiB temporary overlay/build artifacts; no checkpoint duplication.
- Researchers may claim/release the registered bench but may not create, drain, resize, or destroy provider resources.
