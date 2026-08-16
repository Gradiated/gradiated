# Research log

Opened by the Cycle 82 director because the valid r3 denominator changes the numerical gate applied by the older sparse-MoE screens. This is a one-result `$0` rebase, not a patch repair, checkpoint build, or provider-preparation lane.

## 2026-07-16 — ECONOMIC_CLOSE

Question/action: rebased only stock-native top-2 with its shared expert retained and the existing 16-expert/top-2 geometry against the valid exact-workload r3 c16 endpoint. Ran the focused stdlib-only `rebase_sparse_moe_gate.py`; it verifies and records hashes for the fixed r3 summary, native top-2 proxy, and exact geometry artifact. No CUDA, provider, checkpoint mutation, top-2/no-shared repair, or successor preparation occurred.

Evidence: r3 is `552.171055` tok/s. Stock-native top-2/shared has a `6.187016%` ideal summed-work ceiling, yielding only `588.587` tok/s, below the `594.466` target. The 16e/top-2 proxy's `7.775524%` ideal ceiling yields `598.725` tok/s: it crosses the ordinary target, but remains `7.630` tok/s below the required `606.355` (2% margin) nomination boundary. It also requires expert merging/selecting, router retraining, and checkpoint materialization; it is not an exact-stock representation. Kernel fragmentation, routed-work transfer, contextual uncertainty, and missing target-geometry critical-path attribution can only reduce its endpoint transfer.

Decision: **ECONOMIC_CLOSE**. The only raw numerical survivor fails the robustness requirement even under impossible full transfer of a summed-kernel proxy, so no conservative path exists. Artifact: `artifacts/R3_SPARSE_MOE_GATE_REBASE_2026-07-16.json`.
