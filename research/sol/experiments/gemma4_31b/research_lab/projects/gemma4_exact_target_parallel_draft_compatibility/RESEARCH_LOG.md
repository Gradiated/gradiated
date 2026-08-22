# Research log

## 2026-07-29 — exact-target parallel-draft compatibility terminal

Question: Which public DFlash, EAGLE-3, Gemma assistant/MTP, or distinct exact-target path can create accepted tokens for `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4` while preserving greedy target semantics?

Action: Bound the exact target weights/config/tokenizer, DFlash `eabd6483…`, EAGLE-3 `05db845f…`, assistant `627c5ec1…`, SGLang v0.5.13/v0.5.15 source, and the exact c32 runner. Traced each producer through target verification, acceptance, and KV commit. Implemented `exact_target_parallel_draft_adapter.py`, then executed its block-16 consumer and mutation suite. The first test attempt exposed only tuple-versus-JSON-list observer comparisons; preserved it, normalized the result envelope without changing the fixture or acceptance/KV logic, and reran.

Evidence: Nine tests pass, covering every accepted-draft boundary 0–15, target bonus replacement, rejected-suffix noninterference, current-token identity, shape, vocabulary, KV-slot aliasing, and atomic JSON consumption. The measured synthetic fixture returned accepted-draft counts `[15, 0, 2, 7]` with correct `commit_len = accepted + 1`, target bonus, committed input/KV prefix, freed suffix, and pending bonus. Current SGLang source has exact-model registered test contracts for DFlash and official MTP, but those tests and the public weights were not executed here.

Interpretation: DFlash is the only compared public learned path that produces 15 next-token proposals in one forward. EAGLE-3 and Frozen-KV MTP are recurrent and close for this specific one-forward mechanism; NGRAM remains the exact-target, no-draft-model comparator. Config compatibility is necessary but insufficient: DFlash target-revision drift and c32 verifier economics remain live explanations.

Next move: `EXACT_TARGET_PARALLEL_DRAFT_COMPATIBILITY.json` is terminal `promote` for one exact-revision DFlash target-GPU component only. Use its exact launch/workload commands and require accepted target tokens per verifier second, combined draft+verify throughput, NGRAM control, and KV/next-round semantic audits before endpoint promotion. Spend was `$0`; no GPU, provider, endpoint, training, Docker, or SSH action occurred.
