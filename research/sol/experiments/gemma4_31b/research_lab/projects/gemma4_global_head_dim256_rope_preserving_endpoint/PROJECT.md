# Preserve the original rotary subspace in the global head-256 endpoint

## Question

Does the promoted global-head-256 endpoint recover basic language coherence when the ten full-attention layers preserve Gemma 4's original 128-coordinate rotary subspace, while retaining the measured 256-dimensional runtime geometry and performance gate?

## Why this matters

The first actual sliced endpoint completed the exact c32 workload at `0.8354320380624358` seconds/request, `9.13858%` faster than the canonical `0.9194573941250042` control, but all three cheap coherence prompts produced repetitive `laL`-like text. The pinned model uses `global_head_dim=512` with `partial_rotary_factor=0.25`, so the original full-attention rotary width is 128. The sliced endpoint set the global head to 256 but retained factor 0.25, silently reducing the rotary width to 64 and changing the full-layer positional representation. This project tests that specific causal defect before considering training or broad quality evaluation.

## Hypothesis

Keep the exact prior first-256 Q/K/O and Q/K-normalization load-time transform, but set the full-attention candidate's `partial_rotary_factor` to `0.5`. Then `256 × 0.5 = 128`, matching the original rotary width and inverse-frequency grid. If the lost rotary half caused the catastrophic repetition, all three coherence rules should recover without sacrificing the measured endpoint headroom.

## Scope and first scientific arm

Use bench `h200-attention-endpoint-e00vbbb709tzxscaan`, its resident immutable checkpoint, pinned SGLang image, and the prior content-addressed head-256 patch. Before claiming, materialize every bound input inside this project and prove:

- original full attention: head dimension 512, partial factor 0.25, rotary width 128;
- candidate full attention: head dimension 256, partial factor 0.5, rotary width 128;
- original and candidate full-attention inverse-frequency tensors match numerically for the same positions;
- sliding-attention layers, selected weight coordinates, attention scale, backend, and all endpoint settings are unchanged from the promoted candidate.

Claim the warm H200 once, stop only the retained candidate container, and relaunch one patched candidate from the resident read-only checkpoint. Ordinary pre-invocation wiring defects may be repaired in place without changing the intervention. After readiness, run the same three coherence prompts once. If any rule fails, emit a typed coherence negative and stop without invoking the exact-mix runner. If all three pass, prove idle state, flush the cache with HTTP 200, and invoke the frozen c32 runner exactly once.

## Decision gates

- Mechanism oracle: both original and candidate rotary width are exactly 128 and their full-attention inverse frequencies match.
- Transform identity: exactly the same 50 tensors in layers `5,11,17,23,29,35,41,47,53,59`; the checkpoint remains unchanged and read-only.
- Coherence: instruction, arithmetic, and structured-output rules all pass.
- Conditional endpoint: 32/32 valid requests, exactly 17,120 cached and 117,728 fresh prompt tokens, and no reload or retry.
- Performance nomination: service time `<=0.8734845244187539` seconds/request. A smaller valid gain may be retained without tuning.
- Passing coherence and performance nominates this representation for later GPQA-Diamond and TauBench evaluation; it does not itself authorize a quality or production claim.

## Limits

- Finish by `2026-07-18T23:20:00Z` within 50 wall-clock/H200 minutes and `$2.25` provider exposure.
- Use at most 4 GiB temporary storage; reserve 10 minutes for retrieval and release.
- No alternate coordinate set, rotary factor/frequency sweep, dimension/backend/scheduler change, attention-scale change, training, distillation, comparator replay, broad benchmark, checkpoint rewrite, provider allocation, or lifecycle mutation.
- Any post-invocation CUDA/runtime failure, mechanism-oracle failure, or coherence failure is terminal for this line.
- Release the bench without provider teardown and preserve useful resident state.

## Bound evidence and inputs

- Prior promoted/coherence-failed terminal: `../gemma4_global_head_dim256_sliced_endpoint/artifacts/global-head256-sliced-c32-resume-20260718t2225z/TERMINAL.json`, SHA-256 `ffecdc4a6072189e0156463ae8c17c5371124f360c4aaf76cee2855d1cef8142`.
- Prior coherence evidence: `../gemma4_global_head_dim256_sliced_endpoint/artifacts/global-head256-sliced-c32-resume-20260718t2225z/global-head256-sliced-c32-resume-20260718t2225z/coherence.json`, SHA-256 `672d9ecec0cea693fcf03e586cd34e26752fd3bcb1c9654ea6d2ce6d7a095be3`.
- Prior patch manifest: `../gemma4_global_head_dim256_sliced_endpoint/PATCH_MANIFEST.json`, SHA-256 `8f5358f4a2d74af0cbc2cf2b66430b704345f99a2d2f402421184a3c39b8dcf5`.
- Patched model source: `../gemma4_global_head_dim256_sliced_endpoint/patch/gemma4_causal.py`, SHA-256 `45d70e6d3943e349999d7d2a0a8e7e831a9440a7ca367120b58c428750d8da5d`.
- Patched config source: `../gemma4_global_head_dim256_sliced_endpoint/patch/model_config.py`, SHA-256 `ba6a44488466db5667c47c8266d33e79eaebb2b4143e6192b0aeb9ce62837132`.
- Proven owner launcher: `../gemma4_global_head_dim256_sliced_endpoint/launch_owner.sh`, SHA-256 `f4d8389ba3e949ce377185f7d51ed6e1082212200a2808451d7e61c87a98599f`.
- Frozen exact runner: `../gemma4_background_serving_frontier/exact_mix_runner.py`, SHA-256 `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`.
- Model: `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Image: `sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a`.
- Checkpoint: eight files, 62,578,655,208 bytes at `/home/glmrunner/gemma-attention-endpoint/checkpoint`.

