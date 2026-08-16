# Stock-AWQ V2 holdout contract seal

## Question

Can the completed BF16 V2 development control be converted into a frozen, content-addressed post-development holdout instrument that validly orders future BF16-control and current-AWQ candidate captures without transferring development NLL ceilings or mismatched token sequences?

## Why this matters

The campaign's economic work now has exact full-47 endpoints and a live methodology session, but quality graduation gate 1 is blocked because the post-development paired-AWQ design was never frozen and no disjoint holdout exists. The current BF16 ceilings are tied to six development token sequences. BF16 and AWQ tokenizer artifact hashes differ, and no retained hash-bound quantization derivation proves that the two checkpoints are a causal quantization pair. The missing scientific instrument—not another readiness audit—is the highest-value independent `$0` work while the paid owner runs.

## Scope

Work offline at `$0` for at most 900 seconds, 6 GiB RSS, and 32 MiB of new artifacts. Do not call a model, provider, controller, service, or runner; do not prepare a paid command; do not inspect future model responses. Preserve the existing development suite, BF16 adjudication, archives, and terminal quality projects unchanged.

Actually produce and validate:

1. `POST_DEVELOPMENT_QUALITY_POLICY.json` freezing the future control/candidate order and pass/fail rules.
2. A deterministic `build_holdout.py`.
3. `sealed_holdout_v2/holdout.jsonl` with 36 new disjoint cases, exactly six per existing category.
4. `sealed_holdout_v2/MANIFEST.json` binding the builder, holdout, development fixture, BF16 adjudication/archive, BF16 and AWQ checkpoint/tokenizer/chat-template identities, and scorer/transport policy.
5. A validator plus deterministic mutation, category-count, integrity, and development/holdout disjointness tests.

Freeze the future experimental order now:

- Three fresh-process BF16 holdout captures run first with every raw, normalized, transform, runtime-logprob, and token-sequence-hash artifact retained.
- Each holdout teacher-forced NLL ceiling is then frozen as `1.05 * max(mean BF16 NLL across the three captures)` for that exact holdout token sequence.
- Only after valid BF16 control and ceiling artifacts exist may three current-AWQ captures access the holdout.
- BF16 must score at least `5/6` in every category. Candidate rejects on any critical-category regression greater than `1/6`, a fixed-seed category-stratified paired-bootstrap overall lower confidence bound below `-0.05`, any candidate NLL above its sequence-specific frozen ceiling, or missing/invalid evidence.

The BF16 and AWQ tokenizer artifacts differ. For every holdout NLL case, prove exact encoded token-ID equality under both frozen tokenizers and store both token lists/hashes. Generate alternative deterministic sentinel sequences until equality holds. If six valid disjoint NLL cases cannot be produced, return `PAIR_NLL_CLOSE`; do not transfer development ceilings or compare different token sequences.

The known tokenizer JSON difference is the AWQ file's 1,024-token truncation preset; vocab, merges, normalization, pre-tokenizer, post-processor, decoder, added tokens, and chat template are otherwise canonical-identical. Freeze truncation disabled for both identities, record the canonical tokenizer hash under that request policy, and prove identical token IDs for all 36 cases. Treat differing tokenizer-config metadata as identity evidence, not semantic equivalence by assertion.

Label BF16 revision `33faccf4...` versus public-AWQ revision `ab31d120...` as a frozen behavioral-reference eligibility pair, not a causal quantization-only comparison, unless a retained hash-bound derivation is actually found. Sealing means immutable/content-addressed, not secret.

Return `HOLDOUT_CONTRACT_SEALED` only if every named artifact and test passes and the future order is unambiguous. Otherwise return `PAIR_NLL_CLOSE` or `QUALITY_POLICY_CLOSE` with the first exact blocker. Stop after the sealed instrument; do not implement or schedule capture execution in this project.

## Fixed evidence

- BF16 development adjudication: `../bf16_v2_capture_adjudication/`
- Prospective design and frozen development suite: `../quality_gate_calibration/`
- Graduation-packet close/correction: `../stock_awq_graduation_session_packet/`
- Exact current-AWQ model revision: `ab31d120fbe79988fe2a0259993cf3c222aa8881`
- Quality remains mandatory; no economic or provider-beating claim follows from a sealed holdout alone.
