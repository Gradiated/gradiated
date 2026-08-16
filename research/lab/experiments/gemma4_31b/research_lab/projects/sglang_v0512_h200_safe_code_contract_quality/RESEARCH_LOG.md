# Research log

## 2026-07-18 — local pre-create terminal passed

Question: can the final quality intervention be made executable without weakening the safe-Python policy or mutating non-code traffic?

Action: implemented `safe_code_contract.py` and `quality_runner.py`, then ran the pre-create consumer. It serializes all 11 frozen requests, appends the one content-bound contract only to explicit code-only requests, applies the bound adapter after the raw output boundary, and calls the bound strict scorer's sandboxed `executable_score` for all five code tasks.

Evidence: [`artifacts/precreate-terminal/TERMINAL.json`](artifacts/precreate-terminal/TERMINAL.json) is pass=true, SHA-256 `4ea82eaafa23dde2996ebe5a43628dc7b4c28431d15cc98cd5e1d182a1f8f427`. The original seven and four preregistered held-outs (ordering, aggregation, indexing, branching) score 1.0 in the local execution-equivalent fixture. Transformer determinism, non-code byte identity, ambiguous-request non-transformation, unsafe `sorted`, and unsafe import rejection pass. Adapter and strict scorer hashes are bound. Provider spend is $0.

Interpretation: the typed local gate is complete. This is not a model-quality claim; the remaining decision-bearing work is the matched BF16/FP8 capture on a director-owned retained H200 bench.

Next: director to provision and assign one `nvidia-h200-sxm` bench with a 250-GiB disk and the bound SGLang image. No researcher provider creation, GPU claim, or wait is authorized before that assignment.

## 2026-07-18 — final H200 terminal closes the route

Action: preserved the completed matched captures, persisted the strict scorer's return-code-1 payload as its typed negative result, retrieved both raw JSONL files, and ran the direct Transformers sentinel without rerunning either arm.

Evidence: [`artifacts/h200-safe-code-final-20260718t1255z/TERMINAL.json`](artifacts/h200-safe-code-final-20260718t1255z/TERMINAL.json) is pass=false, SHA-256 `72b015851418e83dae04b064103cdad98738bbff9dea3ab67a11d4684bafb3f3`. BF16-KV and FP8-E5M2 both score 10/11: `heldout_ordering` fails in both; all other original and held-out cases pass. Control and candidate NLL are both `0.6548974996976843` (delta `0.0`). The bound direct Transformers sentinel has 240 scored tokens and prompt-token identity=true. The raw capture hashes are retained in the terminal.

Interpretation: this is a model-quality negative, not an operational failure. The explicit safe-code contract did not recover the ordering task in either precision arm; the final SGLang quality route and prepared c64 successor close. Conservatively derived provider exposure is $1.76, within the $3.75 reservation.
