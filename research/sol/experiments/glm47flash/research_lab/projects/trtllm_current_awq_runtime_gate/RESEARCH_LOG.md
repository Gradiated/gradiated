# Research log

## 2026-07-16 — Director opening handoff

- Decision: Open one `$0`, source-only TensorRT-LLM admission gate while the independent n-gram endpoint remains under its exclusive durable provider owner.
- Fixed target: exact campaign AWQ revision `ab31d120fbe79988fe2a0259993cf3c222aa8881` and GLM-4.7-Flash architecture, L40S/SM89, cache-off 8K/1K c16, ordinary `594.466` and robust `606.355` output tok/s.
- First action: Bind one official stable release and fail fast on exact model registration/import before representation or performance analysis.
- Guardrail: No engine build, checkpoint conversion, CUDA, provider action, shared-code edit, or generic-runtime survey. Related-model support and generic TensorRT-LLM speedups are not transferable.

## 2026-07-16 — Official release audit closes at exact model identity

- Question: Does one unchanged current stable TensorRT-LLM release admit the exact pinned GLM-4.7-Flash AWQ checkpoint on L40S/SM89?
- Action: Bound the audit to NVIDIA/TensorRT-LLM `v1.2.1`, tag commit `376f7e1bd8ed543f75014309e3fd4b237e9b0e73`, and hashed the release tree plus the official model registry, GLM model source, and supported-model table. Re-read the named exact checkpoint/config once.
- Measured/source evidence: the checkpoint config declares `Glm4MoeLiteForCausalLM` and `glm4_moe_lite`; v1.2.1 registers and implements `Glm4MoeForCausalLM` only. The supported-model table omits both GLM-4.7-Flash and the exact Lite architecture. Full evidence is in `TRTLLM_RUNTIME_GATE_2026-07-16.json`.
- Interpretation: `MODEL_CLOSE` at gate 1. The exact unchanged loader/import path does not exist in the bound official stable release. Related GLM, generic MoE, AWQ, SM89, or benchmark claims cannot repair an architecture identity mismatch.
- Next move: terminal; no AWQ conversion, engine build, CUDA run, provider mutation, or successor is admissible.
