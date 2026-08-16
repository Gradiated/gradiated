# Research log

Opened by the Cycle 82 director to test the prior output-head project's explicit usage-grounded-shortlist reopen condition. This is a bounded retained-artifact audit and cost falsifier; it owns no provider, checkpoint mutation, training, or controller work.

## 2026-07-16 — CORPUS_CLOSE

Question: Do retained stock current-AWQ archives contain target-representative response tokens sufficient to reopen a vocabulary shortlist?

Action: Audited the two named stock `vllm-awq-batch.tar.gz` archives with `audit_corpus.py`, preserving archive hashes and inspecting only the retained JSON/JSONL members. No CUDA, network, provider, checkpoint, launcher, or token-hash inference was used; cost was `$0`.

Measured evidence: both archives retain the fixed 8K/1K performance rows as request/output counts plus stream hashes, with no response text and no output token IDs. The only raw text is the six `dev_*` quality cases (the teacher-forced case has input token IDs, not generated output IDs) and two identical semantic smoke responses per archive. Cross-archive deduplication leaves 6 unique response texts from 14 text records, all development or semantic-smoke traffic; no target category is present.

Interpretation: `CORPUS_CLOSE`. Coverage, leave-one-group-out stress, exact shortlist representation, and endpoint-transfer stress are inadmissible because the authoritative target traffic has no retained token identities and the remaining text is nonrepresentative. The economic target remains 594.466 tok/s (606.355 robust) versus 552.1710554232396 tok/s, but no shortlist saving is inferred.

Artifact: `artifacts/CORPUS_CLOSE_2026-07-16.json`.
