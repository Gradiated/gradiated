# Research log

Opened by the Cycle 80 director as an independent `$0` runtime/model-structure falsifier. It may not touch the live exit-35 owner or repair the closed patched-forward implementation.

## 2026-07-16 — bounded native constructor/loader falsifier

Question: can stock GLM4-MoE-Lite configuration and checkpoint loading express top-2 routing with no shared expert?

Action/evidence: ran the cached stock Transformers GLM4-MoE-Lite constructor on CPU meta tensors, then exercised loader shape selection against the exact local AWQ index. Both stock (`top_k=4`, one shared expert) and candidate (`top_k=2`, `n_shared_experts=0`) constructors passed. The candidate nevertheless retained the shared module and 138 shared state keys; its shared gate projection is zero-width `[0, 2048]`, while the exact checkpoint's `model.layers.1.mlp.shared_experts.gate_proj.weight` is present and `[1536, 2048]` BF16. `load_state_dict` therefore raised a shape-mismatch error. Omitting the checkpoint keys would require a silent unexpected-key drop or runtime/source loader/forward change.

Decision: **RUNTIME_CLOSE**. The native configuration knob changes router top-k, but no-shared is not a valid exact config/checkpoint-native load state. The derived proxy transfer would be `636.788 tok/s` (`617.315 / 535.286 * 552.171`) versus the `594.466` gate, but it is not admissible because it is based on summed-kernel proxy work rather than a native loaded endpoint. No provider, CUDA, patch repair, successor, or quality claim was made.

Artifact: [NATIVE_PROXY_FALSIFIER_2026-07-16.json](NATIVE_PROXY_FALSIFIER_2026-07-16.json); executable probe: [native_proxy_falsifier.py](native_proxy_falsifier.py).
