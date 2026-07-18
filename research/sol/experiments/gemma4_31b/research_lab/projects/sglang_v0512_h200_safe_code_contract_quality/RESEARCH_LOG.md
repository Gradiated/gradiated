# Research log

## 2026-07-18 — local pre-create terminal passed

Question: can the final quality intervention be made executable without weakening the safe-Python policy or mutating non-code traffic?

Action: implemented `safe_code_contract.py` and `quality_runner.py`, then ran the pre-create consumer. It serializes all 11 frozen requests, appends the one content-bound contract only to explicit code-only requests, applies the bound adapter after the raw output boundary, and calls the bound strict scorer's sandboxed `executable_score` for all five code tasks.

Evidence: [`artifacts/precreate-terminal/TERMINAL.json`](artifacts/precreate-terminal/TERMINAL.json) is pass=true, SHA-256 `4ea82eaafa23dde2996ebe5a43628dc7b4c28431d15cc98cd5e1d182a1f8f427`. The original seven and four preregistered held-outs (ordering, aggregation, indexing, branching) score 1.0 in the local execution-equivalent fixture. Transformer determinism, non-code byte identity, ambiguous-request non-transformation, unsafe `sorted`, and unsafe import rejection pass. Adapter and strict scorer hashes are bound. Provider spend is $0.

Interpretation: the typed local gate is complete. This is not a model-quality claim; the remaining decision-bearing work is the matched BF16/FP8 capture on a director-owned retained H200 bench.

Next: director to provision and assign one `nvidia-h200-sxm` bench with a 250-GiB disk and the bound SGLang image. No researcher provider creation, GPU claim, or wait is authorized before that assignment.
