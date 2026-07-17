# Research log

No researcher result yet. Audit the exact current-AWQ/vLLM MTP payload and return a content-bound executable path plus c16 bound or a closure; do not repeat the historical BF16/SGLang survey.

## 2026-07-15 — pinned current-AWQ loader closure

Question: can the exact layer-47 MTP payload run through the declared vLLM 0.15.0 image and clear the 10% c16 gate?

Action/evidence: ran `content_bound_loader_or_planner_fixture.py` against the local `ab31d120` AWQ cache and the digest-pinned image. The config/index hashes and all 606 layer-47 tensors bind the claim. The image contains `Glm4MoeLiteMTP`, its registry entry, and the `SpeculativeConfig` rewrite to `glm4_moe_lite_mtp`; its `ModelConfig` nevertheless fails before allocation/loading because installed Transformers does not recognize the exact `glm4_moe_lite` config. The 1.543 GiB MTP payload and c16 acceptance/KV bound are in `current_awq_mtp_bound.json`.

Interpretation/decision: source support is not execution support. The immutable runtime cannot bind this exact checkpoint, so this zero-spend project closes without a provider arm. A one-layer MTP would need 0.10 accepted draft tokens/round at zero overhead, 0.155 at 5% overhead, or 0.21 at 10% overhead to reach 588.815 output tok/s; that potential does not overcome the loader closure.

Next move: do not repair or retest this image. Reopen only after a deliberately changed runtime that parses `glm4_moe_lite`, then run the stated one-layer c16 off/on identity and acceptance measurement.
