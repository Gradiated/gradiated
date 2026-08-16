# Research log

Opened by the 2026-07-16 director while the full-model r3 session remains independently owned and live. This project is a single zero-cost local falsifier, not a preparation lineage: it must exercise the real pinned constructor/loader boundary or terminate as `GPU_REQUIRED`, and it may not touch the provider or shared live paths.

## 2026-07-16 — r1 terminal result: resource-bound

**Question/action.** Ran the one bounded local attempt in `exact_loader_falsifier.py` against the read-only student42 v2 root, pinned image `glm-vllm:0.15.0-transformers-1618d44`, network disabled, CPU/meta allocation only, with header-derived fake tensors planned for the real loader and missing/foreign-key controls.

**Measured evidence.** The probe parsed all 24,615 exact safetensors names from four shards without payload reads, resolved the production registry entry `Glm4MoeLiteForCausalLM`, built the exact `ModelConfig` (`num_hidden_layers=42`, `quantization=compressed-tensors`), and entered the real constructor. It stopped before model graph completion at `AssertionError: pipeline model parallel group is not initialized`. Peak RSS was 873,256 KiB (~0.83 GiB); wall time was 22.43 s. The compact artifact binds config/index/manifest/contract and pinned registry, model, quantization, and loader-source hashes: [minimal_depth42_exact_loader_falsifier_r1.json](minimal_depth42_exact_loader_falsifier_r1.json).

**Interpretation.** This is a typed `resource-bound` local result, not loader success: `load_weights`, consumed/missing/unexpected sets, and both negative controls remain unmeasured. It supports the project fail-closed boundary that the real exact route cannot be completed in this CPU-only process without initializing the runtime parallel platform. No provider, live service, shared launcher, checkpoint payload, CUDA, network, training, inference, or successor preflight was touched.

**Next move.** Close this $0 lane. After the named full-model r3 session is reconciled, use a direct L40S load as the only honest next test if r3 does not supersede student42.
