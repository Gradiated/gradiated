# Research log

Scope reminder: test the exact measured serving derivation and layer-47 payload; do not repeat the base-image closure or broaden into other speculative methods.

## 2026-07-15 — Derived runtime binding result

**Question.** Does the exact current-AWQ layer-47 payload bind and plan in the Transformers-derived runtime used by the measured service, without a second full checkpoint?

**Action.** Reused the locally available vLLM 0.15.0 image and its existing derived image layer built from Transformers revision `1618d44b9295361607ec74d7be860ba886aac039`; tagged it with the launcher contract `glm-vllm:0.15.0-transformers-1618d44`. Ran the new content-bound fixture against the exact checkpoint config and index. The fixture does not allocate CUDA or materialize weights.

**Evidence.** [derived_runtime_mtp_binding.json](derived_runtime_mtp_binding.json) records probe exit 0, vLLM `0.15.0`, Transformers `5.3.0.dev0` from the pinned revision, target compressed-tensors config parsing, both target and MTP lazy registry entries, the planner override to `glm4_moe_lite_mtp` / `Glm4MoeLiteMTPModel` with `num_hidden_layers=0` and `n_predict=1`, TP=1, and all 606 layer-47 names mapped to layer 47. The only `embed_tokens` payload rewrites to `model.embed_tokens`, while the remaining MTP names remain under the layer block for the loader. The exact payload is one file, `model-00004-of-00004.safetensors`, 1.543 GiB per the prior manifest. Fixture SHA-256 is `bbff74bc239742d7dbbb1b36d89366a44f711c8f27f623b46ad5427924bf28fb`; result SHA-256 is `836ca75d806fed9a9f3822bf20c9b923497ee9a418fd0959e74dbc7e24811b42`.

**Interpretation.** The base-image closure does not transfer: exact config binding, native planner rewrite, registry resolution, quantization selection, TP contract, shared embedding behavior, and content-bound layer-47 name routing all pass in the actual derived runtime. This supports one later matched L40S c16 MTP off/on arm under the existing gate: 8192/1024 cache-off workload, `num_speculative_tokens=1`, exact output identity, all requests complete, and at least 588.815 output tok/s (10% above the 535.286 c16 control). It does not establish acceptance rate, runtime memory residency, or absence of a second full model allocation; those remain the one-GPU load falsifier and must be measured before any cost claim. No provider spend was used.

**Next move.** Nominate at most one retained L40S c16 off/on arm. If one-GPU load fails for memory, quantization, loader, or output identity, close native MTP for this serving identity; if it loads, measure accepted tokens/round, draft/verify wall time, fallback/errors, VRAM/KV, and exact output identity against the existing economic gate.

## 2026-07-15 — Final-arm interim evidence

**Action/evidence.** The authorized L40S arm `derived_runtime_native_mtp_2026-07-15-r1` reached remote CUDA/Transformers preflight, transferred and verified all four AWQ shards in 367.681 s, and completed native target-plus-MTP model load. The remote snapshot showed CUDA graph capture complete and 43.1 GiB / 46.1 GiB GPU memory used. Native speculative decoding is active, but live vLLM metrics during the fixed batch showed 0–3 accepted tokens per 144–168 drafted (0.0–2.1% acceptance), drafted throughput about 14.4–16.8 tok/s aggregate, and no evidence of an acceleration path versus the 535.286 tok/s stock c16 control.

**Interpretation.** The one-GPU load/residency question passes; the economic mechanism is currently falsified by near-zero draft acceptance and very low observed draft throughput. The fixed runner is still active and has not yet returned the required archive, so this is interim evidence only. Do not promote or run another MTP arm. Reconcile the terminal archive, exact identity, completion fraction, throughput, speculative counters, spend, and verified cleanup before marking the route closed.

## 2026-07-15 — Terminal native-MTP result

**Evidence.** The remote archive [vllm-awq-batch.tar.gz](artifacts/derived_runtime_native_mtp_2026-07-15-r1/vllm-awq-batch.tar.gz) matches its sidecar and local SHA-256 `5f587cb79bba628c237620e10ee9963eb6990611341987ce18b39a1ec27543de`. The exact derived runtime loaded all four AWQ shards and passed health, semantic determinism, and the one-GPU residency gate. During the fixed workload, the engine died with `torch.OutOfMemoryError`: attempted 562 MiB, only 167.38 MiB free, 44.22 GiB in use. The archived `allocation-result.json` records `batch_pass=false`, `performance=null`, and `stream lacks timing or usage evidence`; the preserved server stack identifies the CUDA OOM in the compiled GLM attention path. Reconciliation is [reconciliation.json](artifacts/derived_runtime_native_mtp_2026-07-15-r1/reconciliation.json); instance and disk counts are both zero after cleanup. Exposure was 2,607.296 seconds and derived cost `$0.621494`.

**Decision.** Close native one-layer MTP for the actual current-AWQ derived vLLM/L40S serving identity. This is stronger than the live near-zero acceptance signal: target+MTP can load, but the exact 8,192/1,024 c16 workload cannot produce a complete performance result because MTP leaves insufficient runtime memory and crashes during execution. It fails the 594.466 tok/s promotion gate and does not justify another provider arm or an MTP-specific repair within this project.
