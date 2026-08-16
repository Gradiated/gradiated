# Width-16,384 activation-aware low-rank recovery

## Decision question

Can the fixed, already-measured 21,504-to-16,384 SwiGLU proxy recover basic semantic coherence by merging one activation-aware rank-256 correction into each retained `down_proj`, while preserving the exact inference geometry and latency of the positive width-plus-ring cost floor?

This is a recovery experiment, not a width, rank, channel-selection, runtime, or kernel sweep. The full immutable Gemma 4 checkpoint is the teacher. The fixed 16,384-channel joint-norm selection and exact E5M2 contiguous local ring are the only candidate geometry.

## Evidence and hypothesis

- The exact qualified ring endpoint is `0.6556567115001144 s/request`, still above the H200 economic ceiling `0.6381105231`.
- The fixed width-16,384 plus exact ring endpoint completed 32/32 at `0.6125846611248562 s/request`, but is explicitly quality-unsafe because its simple coherence outputs are incoherent.
- The inference speed is therefore measured; the remaining causal question is whether the discarded-channel MLP output can be approximated with no new runtime operation.

For each of the 60 layers, collect deterministic calibration pairs at the MLP boundary from the original checkpoint and fixed retained-channel proxy. Fit one rank-256 activation-aware residual correction to the retained `down_proj`, then merge the correction into the retained weight. The factorization is a fitting constraint only: no adapter, extra GEMM, hook, or runtime branch may remain at inference.

## Frozen scope

- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Runtime: SGLang v0.5.13 image digest `sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`.
- Accelerator: retained `nvidia-h200-sxm` bench `h200-sync-linear-e00vhh6h29fj68x91g`.
- Width and selection: exactly the bound 16,384 retained channels in `DIRECTOR_BINDING.json`.
- Recovery rank: exactly 256 at every layer; no rank search.
- Serving stack: exact E5M2 contiguous ring on 50 local layers and unchanged paged E5M2 Triton on ten global layers.
- Workload: the campaign content-bound c32 endpoint with exactly 17,120 cached and 117,728 fresh prompt tokens.
- Comparator: the qualified exact-ring endpoint, never the quality-unsafe width-only or width-plus-ring result.

Do not reopen mirrored/split FA3, E4M3, INT4, local-window reduction, NGRAM, scheduler, GEMM schedule, channel selection, width, or rank. Do not duplicate or mutate the source checkpoint.

## Experiment contract

1. Verify `DIRECTOR_BINDING.json` before any paid claim.
2. Build a deterministic, content-bound calibration/holdout split from campaign prompts, with fixed seeds and recorded token/layer sampling. Calibration rows are training evidence, not quality evidence.
3. Capture teacher and fixed-proxy MLP-boundary activations for all 60 layers. Fit exactly one rank-256 residual correction per layer and merge it into the retained `down_proj`. Record solver, precision, conditioning, reconstruction error, and hashes.
4. Test held-out MLP reconstruction and a small preregistered coherence discriminator. It must be finite, nonempty, path-proven, and eliminate the previously observed gibberish/arithmetic failure. Failure closes this representation without an endpoint.
5. Only after that gate, run exactly one recovered-width-plus-ring c32 candidate against the persisted qualified ring comparator. Require 32/32 finite rows, exact cache accounting, all 60 recovered-width paths, all 50 local ring paths, and unchanged ten global paths.
6. A positive endpoint plus the basic coherence gate is a nomination for the campaign's exact GPQA-Diamond and TauBench quality suite. It is not itself production qualification.

No component, standalone width endpoint, ring endpoint, control, or failed FA3 arm may be replayed.

## Terminal decisions

- `reconstruction_or_coherence_reject`: held-out reconstruction is nonfinite/unstable or the fixed basic coherence discriminator fails.
- `endpoint_nonpositive_or_invalid`: coherence passes, but the exact endpoint is invalid or not faster than the qualified ring comparator.
- `quality_suite_nomination`: coherence and exact endpoint pass; preserve the overlay and nominate one later exact campaign quality run.
- `typed_external_blocker`: only after bounded in-place repair cannot reach the frozen scientific invocation.

## Budgets and ownership

- Authorized spend: `$20`.
- Compute: one retained H200, at most six claimed GPU-hours.
- Wall deadline: `2026-07-24T01:15:00Z`.
- Storage: at most 24 GiB of calibration, solver, and overlay artifacts; no checkpoint duplication.
- Provider mutation: forbidden to the researcher. The director owns lifecycle.
- Durable work: if capture or fitting outlives a researcher response, use one bounded local owner in this project and preserve completed stages.

