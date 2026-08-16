# SGLang v0.5.12 safe-code contract quality recovery

## Question

Can a general request-side safe-code contract make the exact Gemma 4 31B checkpoint produce executable policy-safe Python while preserving the measured BF16-versus-FP8 quality parity and every non-code request byte?

## Why this matters

The exact SGLang/H200 FP8-E5M2 endpoint passes the campaign's economic target at `0.3633031778 s/request`, but it is not production-eligible. Its paired quality run failed only because both BF16 and FP8 returned a correct median implementation inside a Markdown fence using `sorted()`, while the bound safe-Python contract intentionally forbids `sorted`, imports, attributes, and other non-whitelisted calls. Six other cases passed, direct-reference prompt-token identity passed, and BF16/FP8 NLL was identical.

The `$0` response adapter correctly refused to unwrap unsafe code, so relaxing that policy or rescoring the old output is closed. This project changes the scientific intervention: add a general, explicit safe-code instruction before generation, then apply the already-bound safe fence adapter after generation.

## Bound identity

Mechanically validate `BINDINGS.json` before requesting a bench. Use the exact checkpoint, immutable SGLang image/runtime, tokenizer/chat template, BF16 control, FP8-E5M2 candidate, raw quality evidence, strict scorer, and adapter terminal. Do not substitute another model, revision, image, KV format, or scorer.

## Local pre-create phase

Build and content-bind one request transformer that activates only when the original request explicitly asks for Python code only. Its appended contract must be task-independent and state that output must contain one function definition, use no Markdown or prose, and call only functions defined in the response plus `min`, `max`, `len`, `range`, `list`, and `tuple`; imports, attributes, `sorted`, and the other bound forbidden constructs remain disallowed.

Preregister at least four held-out code tasks with executable tests before any model call, covering ordering, aggregation, indexing, and branching. Validate locally that:

- non-code requests are byte-identical;
- ambiguous code requests are not transformed;
- the transformer is deterministic and content-addressed;
- the existing adapter and strict safe-Python policy remain byte-for-byte bound;
- request, suite, runner, scorer, checkpoint, image, economics, and deadline identities are recorded in one typed pre-create terminal.

Researchers never create or destroy provider resources. Stop after the local terminal and request a director-owned compatible H200 bench.

## Claimed-bench experiment

On a director-created retained H200 bench, stage and verify the exact checkpoint/image once. Run sequential same-image BF16-KV control and FP8-E5M2 candidate captures with byte-identical transformed requests. Apply the safe adapter only after raw responses are preserved. Include the original seven cases, the four preregistered held-out code tasks, deterministic repetitions, at least 128 teacher-forced tokens, and the direct Transformers reference sentinel.

Require all raw and adapted outputs, request/response hashes, transformation decisions, token IDs/logprobs, per-case executable scores, server identity, telemetry, and an atomic terminal. Every non-code raw request and adapted response must remain byte-identical to the prior capture. The safe-code tasks must pass the unchanged bound AST policy and executable tests in both BF16 and FP8; candidate NLL delta must remain at most `0.03` nats/token.

Repair ordinary launch, API, capture, and retrieval defects in place. Release the bench with its resident-state description; never tear it down. If the quality terminal passes and at least 20 provider minutes remain, release it promptly for the already-prepared c64 project rather than adding an arm here.

## Limits

- Researcher profile: `execution`.
- 120 wall minutes, 85 provider minutes, 1.4167 H200-hours, one director-owned 250-GiB disk, `$3.75` maximum.
- 2 local CPU-hours, 4 GiB project artifacts, 10 GiB retrieved captures.
- No scorer relaxation, weight/checkpoint change, response resampling, MTP, concurrency arm, unrelated prompt mutation, or production claim beyond text-only default non-reasoning with the explicit safe-code contract.

## Portfolio-changing result

A valid pass promotes only the safe-code-contract endpoint boundary and reopens the prepared c64 concurrency measurement. Failure on the original median task, any held-out code task, non-code identity, reference identity, deterministic repetitions, NLL, or safety policy closes the SGLang candidate's remaining quality route and the c64 project without another quality successor.
