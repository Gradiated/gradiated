# Research log

## 2026-07-16 — Director opening handoff

Top-3/shared is a bracketed architecture-cost pass but its complete typed development capture regresses retrieval. Use the three immutable raw archives at the exact existing consumer boundary to decide whether that signal is genuine, ambiguous, or artifact-invalid. No new evaluation or recovery work.

## 2026-07-16 — QUALITY_ARTIFACT_CLOSE

Question: does the completed top4/top3/top4 bracket establish a mutation-scoped retrieval regression through the exact quality consumer boundary?

Action/evidence: verified the three specified `vllm-awq-batch.tar.gz` SHA-256 values once; extracted their persisted quality response/evidence files; and replayed the existing `quality/run_pair.py --mode score`/`score_pair.py` consumer twice, using each top-4 arm as control and top-3 as candidate. Both replays are byte-identical (`8d708ffb…49113`): retrieval `1 -> 0`, overall regression `0.166667`, paired CI `[-0.5, 0.0]`. The consumer rejects an omitted frozen case. Each archive records the same model revision, runtime, suite SHA, six cases, and existing paired result.

Interpretation: close as `QUALITY_ARTIFACT_CLOSE`, not confirmed. The archives preserve normalized `quality-awq-responses.jsonl` plus raw-response hashes in `quality-evidence.json`, but not the serialized raw response bytes. The exact scorer consumes only normalized response files, not raw hashes or identity/evidence records. Thus replay confirms the normalized presentation, but cannot establish the required raw-capture/normalization/identity binding. The inherited absolute-quality failure remains; no deployable-quality conclusion follows.

Artifact: `artifacts/QUALITY_ARTIFACT_CLOSE_2026-07-16.json`.
