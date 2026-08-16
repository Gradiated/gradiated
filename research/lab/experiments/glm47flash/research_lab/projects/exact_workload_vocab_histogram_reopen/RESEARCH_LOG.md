# Research log

## 2026-07-16 — Director opening handoff

- New evidence: the terminal exact current-AWQ n-gram archive contains 32 complete per-request histograms totaling 32,768 output tokens, resolving the prior archive-missingness condition.
- Risk: visible rows are overwhelmingly concentrated in one token and nearly repeat, so exact performance geometry does not by itself establish target-usage diversity or an exact shortlist mechanism.
- Decision: run one bounded `$0` representativeness-first reopen gate. Close on corpus bias or missing exact runtime economics; nominate only at the existing 99.9% leave-group-out and `606.355` robustness thresholds.

## 2026-07-16 — terminal corpus adjudication: CORPUS_CLOSE

- Question: do the 32 complete exact c16 histograms support a target-usage vocabulary shortlist?
- Action: audited the authenticated n-gram archive (`b1a2381cb414a424bddcc3ce2a2b4fc234e397a154616fd15691ea8f13c593c7`) offline with `analyze_histograms.py`; no CUDA, network, provider mutation, checkpoint mutation, or shared-runtime change.
- Measured evidence: 32/32 rows are complete and sum to 32,768 output tokens. There are only 6 histogram signatures and 17 aggregate token IDs; 17 requests have 5 distinct IDs, 14 have 4, and 1 has 16. Token ID 154822 contributes 31,608/32,768 tokens (96.45996%). First/last halves have top-token shares 93.3777%/99.5422%, and a 16-row repeated-pattern block appears 11/13 times.
- Representativeness: the source is one n-gram prompt-lookup arm, hence one method-conditioned independent group. Stream hashes and complete counts do not establish semantic diversity; a 99.9% leave-one-independent-group-out claim is inadmissible. The corpus therefore fails before shortlist representation or economics.
- Terminal decision: `CORPUS_CLOSE`. Exact representation and conservative transfer to `606.355` tok/s were intentionally not tested because the execution contract requires representativeness first. Artifact: `artifacts/CORPUS_CLOSE_2026-07-16.json`.

## 2026-07-16 — Cycle 135 reactivation

The stock knee archive adds five non-speculative histogram groups with 292 distinct streams and 299,008 exact output tokens, satisfying the missing method-free identity condition. Reactivate this project once to determine whether those concurrency groups are genuinely independent target usage or merely the same degenerate synthetic workload. Close before economics if independence fails; otherwise apply the 99.9% coverage, exact fallback, `606.355`, and `1.03x` gates.

## 2026-07-16 — Cycle 135 terminal comparison: CORPUS_CLOSE

- Action: compared the authenticated five-profile unchanged-stock archive (`94e2f841e3a0aa1b4c166e4a4defa20e2b3c5b0cd2ab23f9acc7877ae4d86dbf`) against the prior n-gram archive (`b1a2381cb414a424bddcc3ce2a2b4fc234e397a154616fd15691ea8f13c593c7`) using `compare_stock_ngram.py`. The run was offline, `$0`, with no CUDA, network, provider mutation, checkpoint mutation, or runtime preparation.
- Completeness/identity: all 292 stock rows and all 32 n-gram rows are complete and sum to 299,008 and 32,768 output tokens respectively. Stock has 292 distinct stream hashes, but hashes are identity evidence only and do not establish semantic diversity.
- Measured concentration: stock aggregate token `154822` contributes 278,264/299,008 tokens (93.062%), versus 31,608/32,768 (96.460%) for n-gram. Stock profile top-token shares range from 85.04% (c24) to 97.84% (c30); all five profiles share the same dominant token family and are fixed 8K/1K concurrency repetitions.
- Held-out result: profile-held-out coverage is below 99.9% at shortlist sizes 1, 2, 4, and 8 for every or nearly every profile; it reaches the threshold only around 16–32 IDs. This is leave-one-profile-out, not leave-one-independent-usage-group-out. Concurrency changes scheduling, not the underlying target-usage sample, so the five profiles count as one independent group; the n-gram arm is a second method-conditioned group, not an independent usage corpus.
- Terminal decision: `CORPUS_CLOSE`. The new stock identities confirm corpus degeneracy/under-grouping rather than reopening a shortlist. Exact representation, fallback, `606.355` tok/s, and `1.03x` the `602.157121` control were not tested because representativeness failed first. Artifact: `artifacts/CORPUS_CLOSE_2026-07-16-cycle135.json`.
