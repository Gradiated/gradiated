# Research log — distilled depth-student architecture

## 2026-07-15 — Director delegation

Opened as an independent `$0` physical-student screen after the five-block skip barely reached a 10.42% optimistic ceiling and late-MoE bypass closed at 567.053 tok/s. Bind exactly two students: 39 serving layers (eight sparse blocks removed) for endpoint margin and 34 serving layers (thirteen removed) for the prior c32 KV threshold. Require exact tensor/config manifests, conservative c16/c32 economics, one source-bound pruning fixture, and at least a weak checkpoint-derived recovery prior before nominating any later cost ceiling. No provider, CUDA, shared-launcher edit, training, or quality claim is authorized.

## 2026-07-15 — Physical student screen

Question: does physically removing eight or thirteen complete serving blocks create a credible L40S cost or placement path?

Action: parsed the exact AWQ and BF16 safetensors headers, bound config/index hashes and revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, excluded `model.layers.47` MTP payload, generated deterministic evenly spaced renumbered manifests, and ran a source-bound model-like forward fixture. A bounded memory-mapped sample of BF16 `self_attn.o_proj.weight` supplied a weak adjacent-layer cosine prior; no activation or quality evidence was inferred. No checkpoint shards were transformed and no provider/GPU was used.

Evidence: the 39-layer student removes source layers `[5,10,15,20,26,31,36,41]`, 2.7651 GiB AWQ and 9.4669 GiB BF16 payload, plus 1.125 GiB c16 KV. Its derived c16 peak is 38,843.5 MiB and the fixed-cost endpoint bound is 631.312 output tok/s / `$0.4840/M`, above the 594.466 tok/s / `$0.514/M` gate. The 34-layer student removes `[3,7,10,13,16,20,23,26,30,33,36,39,43]`, 4.4933 GiB AWQ and 15.3837 GiB BF16 payload, plus 3.65625 GiB c32 KV relative to the c16 control. Its derived c32 peak is 45,851 MiB: only 217 MiB below the 46,068 MiB card limit, so allocator fragmentation/runtime workspace can erase admission. Its fixed-cost bound is 711.032 tok/s / `$0.4297/M`, but this is not a measured c32 throughput result.

Interpretation: physical depth is materially stronger than the closed runtime-skip proxy. The 39-layer point has a conservative analytical c16 path, while the 34-layer c32 discontinuity is marginal and should not be the nominated arm. The sampled adjacent BF16 weight cosine is roughly 0.78–0.80 across the stack, which is non-vacuous but only a weak recovery prior and cannot stand in for distillation or quality.

Decision/next move: nominate at most one later, bounded L40S 39-layer cost-ceiling arm, conditional on producing the physical student and running distillation plus the full quality contract. Do not spend provider budget in this zero-cost turn; do not nominate c32 on the 34-layer point without a larger-memory-margin redesign. Artifacts: [`distilled_depth_student_bound.json`](distilled_depth_student_bound.json) and [`source_bound_depth_student_fixture.py`](source_bound_depth_student_fixture.py).

## 2026-07-15 — Materialized student checkpoint

Question: can the nominated 39-layer architecture be materialized as an exact physical AWQ checkpoint with loader closure?

Action: rewrote all four source safetensors shards into `/root/.cache/glm47flash-awq-student39-183247870f89`, copying retained payload bytes, renumbering source layers `[0,1,2,3,4,6,7,8,9,11,...,46]` to `0..38`, removing source layers `[5,10,15,20,26,31,36,41]` and all source layer-47/MTP tensors, and updating `num_hidden_layers`, `mlp_layer_types`, `num_nextn_predict_layers`, and quantization ignore names. Tokenizer and non-weight model assets were copied. The build is content-addressed by manifest contract hash `183247870f8965b8b92260b167eb5c22f486210bf86ffb8a8a4bb0226799caf1`; a second invocation reused the same root and passed again.

Evidence (source-bound, exact static checks): student config has 39 layers and 22,815 consumed tensor keys; the rewritten index has 22,815 entries and exact retained payload byte total; all four output shards have independent SHA-256 hashes. The pinned vLLM identity is `v0.15.0` image digest `97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543`; the existing runtime source screen passes `Glm4MoeLiteForCausalLM` registry mapping and compressed-tensors pack-quantized group-32 route. Local preflight passed model type, quantization route, complete key consumption, no dangling source layer IDs, no layer-47/MTP tensors, and index total-size closure. No CUDA, provider, model load, training, or quality evaluation was performed.

Interpretation: the physical student is now executable in the narrow static sense required for a later runtime arm; the prior analytical cost gate is no longer blocked by checkpoint materialization. This remains a semantics-changing proxy and is not quality eligible. Runtime source inspection cannot prove actual L40S kernel selection or resident-weight loading.

Decision/next move: leave exactly one candidate-only 39-layer L40S c16 cost-ceiling action queued behind the active adaptive-MoE terminal. Require the later arm to use this content-addressed root, preserve the pinned vLLM/workload identity, and collect full quality and economic telemetry before any distillation or deployable claim.

## 2026-07-15 — Loader-contract falsification; close at zero

Question: can the admitted shared `vllm_smoke_control.py` safely execute the materialized student without a launcher edit or fabricated checkpoint identity?

Action: added the missing student `model-files-manifest.json`/`model-files.sha256`, ran the actual shared `awq_smoke_control.validate_local_model`, and ran the pinned local `glm-vllm:0.15.0-transformers-1618d44` preflight with the student config. No provider create was attempted.

Evidence: the student manifest is internally exact at 4 shards and 15,544,868,264 weight bytes, but the shared launcher is hard-coded to the control geometry 20,170,199,928 bytes and returns `AwqSmokeError: local model weight bytes mismatch` before any provider mutation. The local pinned container imports vLLM/Transformers and parses the config, then terminates at the expected CUDA probe with `RuntimeError: No CUDA GPUs are available`; this is an environment diagnostic, not a loader success. The declared remote script hash `afab442b...` also differs from the current file hash `138c68a...`, so the paid identity is not safely bound.

Interpretation: the prior structural preflight overclaimed loader closure. The only routes to a paid measurement are an explicitly authorized shared-launcher contract correction plus a refreshed remote-script identity, or a different proven launcher. Editing the shared launcher, padding/fabricating the manifest, or creating the provider session now would make the result uninterpretable and violates the continuation contract.

Decision: close this lineage at `$0`; provider create was not attempted and no quality or economic result exists. Diagnostic: [`student39_loader_contract_diagnostic.json`](student39_loader_contract_diagnostic.json). Corrected status: [`student39_runtime_preflight.json`](student39_runtime_preflight.json).

## 2026-07-15 — Measured 39-layer L40S cost proxy

Question: does the exact physical 39-layer AWQ student clear the `594.466` output-token/s architecture-promotion gate on the campaign's fixed 8K-input/1K-output workload?

Action: admitted the content-addressed derived checkpoint in the shared launcher, loaded it on one Nebius L40S, and measured c16, c24, and c32 with two full batches at each concurrency. The first allocation failed on a manifest-contract comparison. The retained retry loaded the model but exposed two stale remote-runner assumptions: an allowlist that rejected `16,24,32`, followed by an unused c8 lookup after all three profiles had completed. The parser now accepts any positive strictly increasing frontier, the unused c8 lookup is removed, and focused tests cover both contracts. The final performance summary was deterministically recovered from the completed raw profile artifacts before packaging. The unrelated long methodology sweep was stopped; the instance and managed disk were deleted and absence verified.

Measured evidence: all 144 requests completed with exact 8,192-input/1,024-output geometry and prefix-cache zero deltas. c16 produced `674.424` output tok/s in `48.587` seconds, c24 produced `661.661` tok/s in `74.286` seconds, and c32 produced `734.557` tok/s in `89.218` seconds. At the `$1.10/L40S-hour` planning rate these are `$0.453062/M`, `$0.461801/M`, and `$0.415973/M`; all clear the `$0.514/M` gate. Relative to the matched 47-layer c16 control at `535.286` tok/s, c16 improves throughput by `25.993%` and planning cost by `20.631%`; c32 improves throughput by `37.227%` and planning cost by `27.128%`. The repaired arm recorded `212.091` useful GPU seconds, artifact SHA-256 `f9f3f77da53d30e87604d8a0f8c1ddd81e8bed65bab100896b06b5c6a7b35383`, and verified cleanup. Derived total provider exposure across the two created instances is approximately `$0.766828`, within the `$1.00` project cap.

Interpretation and decision: physical depth reduction passes the cost-mechanism screen decisively. The terminal archive remains labeled `SCIENTIFIC_FAIL` because the untrained student failed the intentionally deferred quality diagnostic and c24/c32 miss the inherited interactive TTFT threshold; neither invalidates this background cost proxy. Do not claim deployable or quality-adjusted economics. Promote the mechanism to a separate recovery/distillation project using this exact 39-layer checkpoint, then run the full quality and provider-matched graduation contracts only after recovery. Artifact root: [`artifacts/nebius_l40s_student39_c16_c24_c32_2026-07-15-r2-repair02`](artifacts/nebius_l40s_student39_c16_c24_c32_2026-07-15-r2-repair02).
