# Stock-AWQ holdout scoring seal repair

## Question

Can the byte-valid 36-case post-development holdout be repaired into one execution-complete, content-addressed scoring contract whose BF16 and AWQ evidence has exactly one possible pass/fail interpretation?

## Why this matters

The predecessor produced useful immutable content: 36 disjoint cases, six per category, exact BF16/AWQ token-ID equality with truncation disabled, and a deterministic builder. A director audit found that `HOLDOUT_CONTRACT_SEALED` was nevertheless too strong. The policy does not define repeated-capture aggregation, ordinal pairing, the bootstrap resampling unit, or whether the BF16 `5/6` floor applies per capture. It also omits exact request settings and a concrete scorer; the holdout's loss cases omit the runtime runner's `token_sequence_sha256` field. Identical future evidence could therefore receive different decisions.

This bounded `$0` repair is the direct blocker to the next quality experiment. Do not reopen content ideation or perform runner/provider preparation here.

## Scope and resource contract

Work offline for at most 1,200 seconds, 6 GiB RSS, and 48 MiB of new artifacts. Do not call a model, provider, controller, service, or runner. Do not inspect future model outputs or alter the completed predecessor artifacts. Reuse their content by hash.

Produce a successor instrument in this project:

1. `POST_DEVELOPMENT_QUALITY_POLICY_V2.json` with one fully specified decision function.
2. `build_resealed_holdout.py` and `sealed_holdout_v3/holdout.jsonl`, preserving all 36 predecessor case semantics while adding one canonical runtime token-sequence hash definition compatible with the quality runner.
3. `sealed_holdout_v3/MANIFEST.json` binding the predecessor builder/holdout/policy, development fixture and manifest, BF16 adjudication/archive, both exact checkpoint revisions/manifests, tokenizer JSON/config/chat-template/canonical identities, the new builder/policy/fixture, scorer, request contract, and encoding runtime.
4. An executable deterministic scorer/bootstrap implementation and fixtures that prove a unique decision on synthetic evidence only.
5. A fail-closed validator and mutation tests covering every claimed binding, decision boundary, request setting, payload disjointness, token-ID/runtime-hash convention, and deterministic rebuild.

Freeze these semantics unless an implementation impossibility forces `QUALITY_POLICY_CLOSE`:

- Three fresh server-process captures per model, indexed `0..2`. Each capture makes exactly one request per case. AWQ remains forbidden until all three BF16 captures validate and the six loss ceilings are frozen.
- Every BF16 capture must independently score at least `5/6` in every category. Do not replace this with a pooled threshold.
- For each case and model, the point score is the arithmetic mean of its three binary capture scores. Category scores are the mean of the six case point scores. Critical-category regression is AWQ minus BF16 and rejects when less than `-1/6`.
- Pair BF16 and AWQ by capture ordinal and case ID. In each seeded bootstrap replicate, sample six case IDs with replacement independently within each category; keep all three ordinal capture pairs for each sampled case as one cluster, average the resulting 18 paired deltas per category, then equal-weight the six category means. Use seed `470236`, 10,000 replicates, the exact deterministic PRNG/quantile convention implemented by the scorer, and reject if the 0.025 lower bound is below `-0.05`.
- For every loss case, the BF16 ceiling is `1.05 * max(mean NLL in capture 0, capture 1, capture 2)` over the exact scored runtime token IDs. Reject AWQ if any ordinal capture's mean NLL exceeds that case ceiling. Define exactly how the unscored first token and returned token-ID list are handled.
- Bind generation requests to the proven runner contract: non-streaming `/v1/chat/completions`, `temperature=0`, `top_p=1`, `max_tokens=256`, seed `470200`, and thinking disabled; loss requests use non-streaming `/v1/completions`, `temperature=0`, `max_tokens=1`, `prompt_logprobs=1`, and returned token IDs. Freeze model alias, message construction, normalization, finish-reason, timeout, and missing-evidence behavior.
- Define the runtime sequence hash as SHA-256 over one named canonical serialization of the exact token IDs and require the returned IDs to equal the stored BF16/AWQ list. Store that single hash in every applicable V3 case and prove it matches both lists.

Payload disjointness must cover case IDs and all content-bearing prompt, history, context, teacher-forced, expected-answer, and test payloads—not only whole-row equality or a sentinel substring. Validation must recompute actual hashes rather than trust manifest values. Include positive scorer fixtures and mutations that independently exercise per-capture BF16 failure, critical regression, bootstrap threshold, NLL ceiling, ordinal pairing, request drift, tokenizer/checkpoint identity drift, builder drift, development/adjudication drift, token IDs/hash drift, and payload overlap.

Return `HOLDOUT_CONTRACT_RESEALED` only when a clean rebuild is byte-identical and every validator/scorer/mutation test passes. Otherwise return `QUALITY_POLICY_CLOSE` with the first exact blocker. Stop at the instrument; no capture execution or paid-command preparation is authorized.

## Fixed evidence and claim limits

- Predecessor: `../stock_awq_holdout_contract_seal/`
- Development suite: `../quality_gate_calibration/executable_development_v2/`
- BF16 adjudication/archive: `../bf16_v2_capture_adjudication/` and `../bf16_vllm_quality_bridge/`
- BF16 revision: `33faccf4c2ba82142214d0d4e16232a4e9ccfe10`
- AWQ revision: `ab31d120fbe79988fe2a0259993cf3c222aa8881`

The pair remains behavioral-reference eligibility only, not a causal quantization comparison. A resealed instrument is not model-quality evidence.

## Director executable-seal correction — Cycle 123

Reject the reported `HOLDOUT_CONTRACT_RESEALED` as a terminal result. The V3 bytes remain useful, but the claimed executable decision function fails its first real serialization boundary: JSON turns capture ordinal keys into strings while `score_resealed_holdout.py` requires integer keys. More importantly, that scorer trusts precomputed `pass` booleans and synthetic logprob lists rather than consuming the seven-file capture contract bound in its own manifest. It does not derive case scores from raw/normalized outputs or prove request, checkpoint, model-alias, fresh-process, runtime-token, or repetition identities. The validator also accepts drift in BF16 revision, model alias, normalization, and canonical-token convention, and its combined payload projection does not enforce field-level disjointness. Six serving cases retain `deterministic_repetitions=2` while the policy says one request per case.

Reactivate this same project for one final `$0` executable bridge; do not create another seal/readiness successor. Work for at most 1,200 additional seconds, 6 GiB RSS, and 48 MiB additional artifacts. Provider/model/controller/service use remains prohibited. Narrow shared-runner and focused-test edits are allowed only when required to make the already-preregistered H100 capture bytes satisfy this contract.

The correction must:

1. Use a canonical JSON-list capture schema or explicitly normalize serialized ordinal keys, with a CLI round-trip test over on-disk JSON.
2. Adapt the proven `bf16_v2_capture_adjudication/adjudicate_bf16_v2_capture.py` logic to consume each real seven-file capture directory. Derive every binary score from frozen holdout scorer content and every NLL from aligned runtime token IDs/logprobs; never accept caller-supplied pass/fail or precomputed NLL.
3. Verify raw-response row hashes, canonical normalized aliases, transform/runtime bindings, exact case/repetition coverage and order, model revision/manifest/alias, suite/policy/runner hashes, request fields, finish/truncation behavior, and three distinct fresh server-process identities.
4. Make the bound `vllm_v2_quality_runner.py` emit the evidence needed for those checks, including returned runtime prompt token IDs and their recomputed canonical hash rather than copying a suite hash. Resolve `deterministic_repetitions=2` consistently in the policy, fixture, runner, scorer, and geometry; do not silently ignore it.
5. Recompute every manifest claim and reject independent mutations of checkpoint revisions, model alias, normalization, request contract, canonical token serialization, runner/scorer/validator/builder/development/adjudication bindings, individual content-bearing field overlap, raw/normalized evidence, process identity, repetition geometry, token IDs/hash, and decision thresholds.
6. Prove the ingestion path with the immutable real r4 BF16 development seven-file captures, reproducing their existing adjudicated category scores and NLL ceilings, plus synthetic holdout boundary fixtures. A fake-only scorer pass is insufficient.

Return `HOLDOUT_EXECUTABLE_BRIDGE_PASS` only when clean deterministic rebuild, CLI JSON round trip, real-archive ingestion, validator, scorer, and every mutation test pass and the exact H100 runner inputs are content-bound. Otherwise return `QUALITY_POLICY_CLOSE` and close this quality route without another repair project. Stop before provider mutation; `bf16_v2_holdout_controls` remains blocked until this result and authenticated AA cleanup are both true.
