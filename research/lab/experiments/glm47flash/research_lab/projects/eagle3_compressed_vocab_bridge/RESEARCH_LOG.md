# Research log

## 2026-07-16 — Director opening handoff

- Decision: Follow the broad draft gate's terminal identity result with one narrower audit of the exact-model EAGLE3 checkpoint's compressed-vocabulary semantics; no second candidate search.
- Why reopened at portfolio level: the discovered candidate reports `54.9%` acceptance and `1.66x` on H200, while its `draft_vocab_size=32000` may denote an internal proposal space with an exact target-ID mapping rather than a tokenizer.
- First action: prove or falsify the mapping from bounded official weight metadata plus pinned vLLM source. Stop before runtime/memory/economics if it does not bind exact target IDs.
- Guardrail: No full weight download, CUDA, patch, provider action, controller preparation, conversion, or training.

## 2026-07-16 — Mapping audit terminal result

- Question/action: Read only the safetensors header plus the two small mapping tensors from the pinned official candidate, then audited the v0.15.0 source tree. No full payload, CUDA, provider, or spend.
- Evidence: `model.safetensors` declares `d2t` `[32000] I64` and `t2d` `[154880] BOOL`. The measured contract is `target_id = draft_index + d2t[draft_index]`; all 32,000 derived IDs are unique and in `[0,154879]`, and their set exactly equals the 32,000 true entries of `t2d`. Hashes and bounded ranges are in `eagle3_mapping_runtime_audit_2026-07-16.json`.
- Runtime evidence: pinned vLLM `llama_eagle3.py:351-355` explicitly consumes `d2t` as `draft_id_to_target_id`, ignores `t2d`, and expands logits into the target vocabulary. However, unchanged `speculative.py:666-678` admits EAGLE3 only for target model types containing `llama`, `qwen`, `minicpm`, or `gpt_oss`; the exact target config is `glm4_moe_lite`.
- Decision: `RUNTIME_CLOSE`. The mapping hypothesis is proven, but the exact target/draft pair is rejected by the unchanged pinned runtime before load. c16 residence and economics remain unmeasured by the declared fail-fast order.
