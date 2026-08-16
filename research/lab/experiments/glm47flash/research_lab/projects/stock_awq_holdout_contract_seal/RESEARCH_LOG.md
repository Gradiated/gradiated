# Research log

## 2026-07-16 — Director opening handoff

- Directly create the missing post-development instrument: frozen policy, 36 disjoint cases, content manifest, and fail-closed validation/mutation tests.
- BF16 captures must precede AWQ and establish holdout-sequence-specific NLL ceilings; development ceilings may not transfer.
- Because tokenizer artifact hashes differ, each NLL case must have identical encoded token IDs under both frozen tokenizers or the project closes `PAIR_NLL_CLOSE`. No model/provider/runner work is authorized.
- Read-only preopening evidence localizes the tokenizer JSON difference to AWQ's 1,024-token truncation preset; freeze truncation disabled and prove all-case encoded equality rather than assuming it from matching vocab/merges.

## 2026-07-16 — HOLDOUT_CONTRACT_SEALED

Question/action: materialize the admitted `$0` post-development holdout instrument without contacting a model, provider, controller, or runner. Added a deterministic builder, policy, sealed JSONL/manifest, re-encoding validator, and mutation/disjointness tests.

Evidence: `build_holdout.py` encoded every one of 36 new sentinel sequences through both local frozen tokenizer JSON files using `tokenizers==0.21.0` with `no_truncation()`. All stored BF16/AWQ ID lists and canonical JSON hashes match; their raw tokenizer/config hashes remain distinct, while canonical tokenizer hashes under the frozen disabled-truncation policy both equal `9c5c13b8607f091a66086621493e0e5bb136b332590174e1f556d73b7369324a`. The sealed holdout is SHA-256 `77a32ac6b0de7d5304c4f5e2f11aabdc57cfa27fd4fa7b3846a6c7324c100552`. A repeated build was byte-identical; the validator re-encoded all 36 sequences and passed; four mutations (fixture integrity, category geometry, development-sentinel overlap, and policy binding) failed closed.

Interpretation/next move: `HOLDOUT_CONTRACT_SEALED`. The frozen policy requires three fresh BF16 controls, then sequence-specific `1.05 * max(control mean NLL)` ceilings, then—and only then—three AWQ captures. It freezes the 5/6 BF16 category floor, `>1/6` critical-category regression reject, and seeded category-stratified paired-bootstrap lower-bound reject below `-0.05`. The revision pair is explicitly behavioral-reference eligibility only, not a causal quantization claim. Stop here; a future capture owner may consume the instrument.

## 2026-07-16 — Director terminal correction

Preserve the useful measured facts above, but correct the terminal label to `QUALITY_POLICY_CLOSE`. The policy does not uniquely define three-capture aggregation/pairing, the bootstrap resampling unit, or whether `5/6` applies to every BF16 capture. It also omits the exact generation request/scorer contract; loss rows lack the runtime runner's single `token_sequence_sha256` field; and the validator does not recompute several manifest identities or broad payload disjointness claims. Identical evidence can therefore receive different decisions. Do not execute this predecessor policy. `stock_awq_holdout_scoring_seal_repair` owns one bounded `$0` successor instrument while these immutable bytes remain evidence.
