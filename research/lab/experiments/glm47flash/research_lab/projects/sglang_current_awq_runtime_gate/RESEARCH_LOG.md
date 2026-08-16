# Research log

## 2026-07-16 — Director opening handoff

- Decision: Replace the terminal TensorRT-LLM audit with one independent `$0` SGLang current-release gate while n-gram remains under its exclusive durable provider owner.
- Fixed target: exact AWQ revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, L40S/SM89, cache-off reasoning-disabled 8K/1K c16, ordinary `594.466` and robust `606.355` output tok/s.
- First action: Bind one official stable SGLang identity and decide whether `Glm4MoeLiteForCausalLM` is stock-supported; the old patched V14 smoke is only a compatibility prior.
- Guardrail: No patch, engine/image build, model load, CUDA, provider action, controller preparation, or generic runtime claim.

## 2026-07-16 — Terminal source/runtime gate: REPRESENTATION_CLOSE

- Question: Does one unchanged current stable SGLang release admit the exact campaign AWQ checkpoint on L40S?
- Action: Bound official `v0.5.15.post1`, published 2026-07-14, annotated tag `658e0a9…`, commit `0b3bb0c…`; compared its raw model and loader source with the retained 0.5.15 smoke identity and patch manifest.
- Evidence: Stock `glm4_moe_lite.py` contains `EntryClass = [Glm4MoeLiteForCausalLM]`, so exact model registration passes. The exact AWQ smoke then fails in stock `deepseek_weight_loader.py:522` at `self_attn.kv_b_proj.weight` with `AttributeError: 'ColumnParallelLinear' object has no attribute 'weight'`. The retained run used SGLang 0.5.15 on L40S SM89 and required patches to `glm4_moe_lite.py` and `deepseek_v2.py`; their pre-patch hashes match the bound stock source. Raw diagnostic and patch manifest are retained under `evidence/phase3-attempt2/phase2-awq-smoke/`.
- Interpretation: `REPRESENTATION_CLOSE` at gate 2. Exact architecture support exists, but unchanged exact compressed-tensors AWQ/MLA execution does not. The old 18,587-MiB memory observation is patched compatibility evidence, not an admissible exact runtime result. SM89 execution, semantics/memory, and economic gates are not reached.
- Next move: Terminal; no patch, image, model load, CUDA run, provider mutation, or successor is admissible.
