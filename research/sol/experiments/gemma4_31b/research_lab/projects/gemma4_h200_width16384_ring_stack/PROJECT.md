# Width-16,384 plus contiguous-ring interaction on H200

## Question

Do the two measured endpoint gains compose when the frozen quality-unsafe 16,384-wide MLP proxy and the byte-exact E5M2 local ring run in the same SGLang v0.5.13 c32 endpoint?

## Evidence and importance

The width proxy completed 32/32 requests at `0.6323543743435494 s/request`, 6.2242% faster than its persisted `0.6743258590313417` control and already below the `0.6381105231` H200 ceiling. Its simple coherence outputs were incoherent, so it is an execution proxy and not production-eligible.

Independently, the repaired ring completed 32/32 requests at `0.6556567115001144 s/request` versus `0.6766461551248995`, a 3.1020% reduction. Its fresh extend, first two decode transitions, ownership, padding, and semantic discriminator passed. Applying that measured fraction to the width endpoint predicts `0.6127388538966473 s/request`, but only an actual combined endpoint can establish interaction.

## Immutable scope

- Reuse the exact model, checkpoint, SGLang commit/image, c32 workload, token accounting, width selection, width overlay, and ring producer/consumer paths bound in `DIRECTOR_BINDING.json`.
- The candidate changes only those two already-measured interventions. No width, channel selection, ring layout, window, KV dtype, attention backend, batching, or runtime setting may change.
- The persisted width endpoint is the primary incremental comparator. Also report the combined delta from the qualified `0.6743258590313417 s/request` control.
- This arm remains explicitly quality-unsafe. It measures interaction and a hardware cost floor; it cannot authorize deployment or a quality claim.

## Immediate experiment

After the `$8` reservation is durable, claim `h200-sync-linear-e00vhh6h29fj68x91g`. Reuse the two proven launchers and overlays to build one combined server. Do not replay either standalone component, standalone endpoint, or control.

Run the existing small transition/path checks needed to prove all 180 width-modified MLP projections and all 50 local ring routes are active while the ten global attention layers and every other path remain unchanged. Then run exactly one profiler-off c32 candidate. Require 32/32 finite rows, exact 17,120 cached plus 117,728 fresh prompt-token accounting, ring transition proof, and both intervention path audits. Record the incremental delta against the persisted width terminal and the total delta against the qualified control.

Close on non-finite execution, path absence, invalid accounting, semantic failure beyond the already-declared width incoherence, or endpoint regression against the width terminal. Retain any reproducible positive incremental gain.

## Resources

- Researcher profile: `execution`.
- One retained H200; at most 45 claimed GPU-minutes and 75 wall minutes.
- Absolute execution deadline: `2026-07-23T18:00:00Z`.
- Authorization: `$8.00`.
- At most 12 GiB temporary overlay/build artifacts; no checkpoint duplication.
- Researchers may claim and release the registered bench but may not mutate provider lifecycle.
