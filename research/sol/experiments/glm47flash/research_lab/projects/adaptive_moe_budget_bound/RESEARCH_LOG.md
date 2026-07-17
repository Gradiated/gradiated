# Research log

No researcher result yet. This is a zero-cost, source-and-artifact-bound feasibility project; do not execute provider/GPU work or revive the terminal fixed top-2/no-shared delivery route.

## 2026-07-15 — Source-bound confidence-policy falsification

**Question.** Does the exact current AWQ/vLLM evidence support a confidence-qualified top-2/no-shared path with enough qualifying token-layer decisions to clear the c16 cost gate?

**Action.** Added and executed the CPU-only [policy fixture](source_bound_policy_fixture.py), bound to the exact config and retained combined MoE proxy. It expresses stock top-4-plus-shared, top-2-plus-shared, and top-2/no-shared on one 64-expert token-layer decision, computes the qualifying-fraction/overhead curve, and audits the retained current-runtime artifacts for actual router observability. The decision artifact is [adaptive_moe_budget_bound.json](adaptive_moe_budget_bound.json).

**Evidence.** The exact config has 46 sparse layers, 64 routed experts, stock normalized top-4 (`noaux_tc`) routing, and one separate shared expert. The retained trace proxy's combined ideal ceiling is 13.2881% while the economic gate is 9.9551%, so zero policy/dispatch overhead needs 74.9179% qualification; just 1%, 2%, and 3% overhead raise that requirement to 82.444%, 89.971%, and 97.497%. No exact-current router logits, selected-expert weights, margins, entropy, or per-token grouped-GEMM assignments were retained. The pinned observer only records scheduler composition/NVTX ranges, not MoE router statistics.

**Interpretation and next move.** Close this line. The existing evidence cannot establish the required qualifying fraction, and a new MoE-forward statistic/export hook is not an existing cheap observer; its synchronization and wall-time cost would consume the 3.3329% maximum overhead budget before it answered the question. Do not invent a router distribution or create a provider/GPU arm. Reopen only under a separately admitted observer project that first proves an exact source-bound, non-synchronizing router summary path.
