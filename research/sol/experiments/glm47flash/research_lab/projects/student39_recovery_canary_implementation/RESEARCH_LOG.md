# Research log

Delegated in Cycle 56 because the 26-GPU-hour recovery proposal references an unimplemented trainer. Make the real cache/loss/LoRA/checkpoint path executable and return one <=4-GPU-hour canary or close at `$0`; do not allocate, download training data, or touch the holdout.

## Cycle 57 — source-bound contract and zero-cost terminal decision

Question: can the exact student39 recovery path be exercised before provider work?

Action: added `student39_recovery.py`, a fail-closed source binder for the local BF16 teacher and exact 39-layer student, cache schema validator, KL plus eight-bridge loss, checkpoint save/reload/resume path, and four negative controls. The same code ran a dependency-free tiny fixture for two optimizer steps and resumed at step 3. It recorded finite losses `0.030669 -> 0.029923 -> 0.030871`; checkpoint reload passed and the W4 contract remained symmetric group-32. Source binding measured the required class/config/depth mapping and SHA `e501ab...accb3a`.

Evidence: `STUDENT39_RECOVERY_CANARY_PREFLIGHT.json`. Exact cache payload is `33,152` bytes/token: 256-byte top-64 IDs, 128-byte top-64 BF16 logits, and 32,768-byte eight×2048 BF16 bridges. At 250,000 tokens this is `8,288,000,000` bytes (`7.715 GiB`), with a conservative `9.26 GiB` free-disk requirement.

Negative controls rejected mapping, teacher revision, top-64 shape, and malformed checkpoint drift. No training corpus, frozen development data, or holdout was read. The real Transformers/PEFT model construction could not run because the host lacks `torch`, `transformers`, `peft`, and `safetensors`; this is a typed zero-cost external-runtime blocker, not model evidence. Therefore no canary is nominated and the project closes at `$0`; no provider mutation occurred.

## Cycle 58 — real pinned-image discovery and terminal canary decision

Question: does the existing local runtime make the recovery path genuinely executable?

Action: built `student39-peft:0.19.1` from base image `glm-vllm:0.15.0-transformers-1618d44@sha256:4672d4aa966cf5f4d437d9f7fd9fb4d1b662a067455f3db46d2ab6cce3f3f62c`; the only added package was pinned `peft==0.19.1`, derivative digest `sha256:4e7d66c0f29301823701f466ca485c5ddde7c6e48fff3eadb900c4bb2cc2f0d3`. Ran the project’s same entrypoint with `--real-meta-run`, no CUDA and no model/data download.

Measured: real `Glm4MoeLiteForCausalLM` construction produced a 39-layer student and 47-layer teacher. PEFT discovered 1,395 LoRA modules with exactly 11,188,224 trainable and 24,860,900,096 frozen parameters. Sixteen actual layer hooks (eight student/teacher bridge pairs) registered. Real torch tensors matched top-64 `[1,1,64]` IDs/logits and bridge `[1,1,2048]`; KL `1.2771906853`, bridge MSE `1.9136749506`, total `1.7556093931`, finite. A safetensors cache shard had deterministic duplicate hashes; adapter checkpoint reload passed and resumed at step 3. Same-entrypoint negative controls rejected cache and checkpoint mapping drift. The CPU gemm warning about optional `kernels` was non-fatal and no forward pass was attempted on meta weights.

Decision: source/runtime/cache/loss/checkpoint readiness passes, but the required BF16 V2 control is not adjudicated: `quality_gate_calibration` records V35 as a terminal adapter defect with zero capture phases and no frozen NLL ceilings. The canary must therefore remain gated and is not nominated. Close at `$0`; no provider, corpus, development, or holdout action occurred. Reopen only after fresh BF16 ceilings exist.
