# SGLang v0.5.12 output-contract adapter

## Question

Can a narrow, deterministic endpoint adapter satisfy an explicit code-only response contract for the exact SGLang/H200 candidate without changing unrelated response content or erasing the BF16-versus-FP8 quality comparison?

## Why this matters

The economically passing FP8-E5M2 candidate remains non-production-eligible because the preregistered paired-quality terminal failed. That failure is not candidate-specific: BF16 and FP8 produced the same functionally correct `median` implementation, wrapped in one Markdown `python` fence, and both failed the intentionally strict executable scorer. All other six cases passed in both arms, direct-reference prompt-token identity passed over 240 tokens, and candidate/control NLL was identical at `0.6548974997` with delta `0.0`.

Raw SGLang output must remain classified as failing. This project tests a genuinely different product intervention: a transparent response-contract boundary for requests that explicitly require Python code only.

## Bound evidence

Use `BINDINGS.json`. Consume the immutable raw BF16 and FP8 captures, reference sentinel, failed paired terminal, case definitions, and the bound strict scorer. Do not regenerate model output, alter captured bytes, change the suite, or use a provider GPU.

## Intervention and acceptance

Implement a content-addressed adapter with one narrow transformation:

- The request must explicitly require Python code only.
- The response must contain exactly one outer fenced code block labeled `python` or unlabeled, with only surrounding whitespace and no prose or second block.
- The extracted body must pass the bound scorer's safe-Python AST restrictions before transformation.
- Every other response must be byte-identical after the adapter boundary.

Apply the identical adapter to both BF16 and FP8 capture streams, then run the exact executable/NLL scorer and direct-reference checks. Preserve original bytes, adapted bytes, request hashes, transformation decisions, and output hashes. Add independent negative fixtures for mixed prose, multiple blocks, unsupported languages, malformed fences, unsafe Python, imports, attributes, and ambiguous requests; all must remain unchanged or be rejected. Do not special-case the observed function or expected assertions.

Measure adapter CPU wall time over at least 100,000 mixed transformed/untransformed responses. Require p99 overhead at most `1 ms/request` and derived service-time impact below `0.3%` of the measured `0.3633031778 s/request` candidate.

## Scope limits

- Researcher profile: `execution`.
- 45 wall minutes, 2 local CPU-hours, 1 GiB, `$0` provider spend.
- No GPU claim or creation, checkpoint work, model call, prompt/template mutation, resampling, scorer relaxation, MTP, concurrency measurement, or broad quality claim.
- Raw SGLang remains ineligible. Any pass applies only to the adapter-enabled, text-only, default non-reasoning service boundary and this bound suite; vision, reasoning, broad safety, long-horizon reliability, and MTP remain unvalidated.

## Portfolio-changing result

A passing atomic terminal must show both adapted control and candidate pass every bound case, unchanged NLL/reference evidence, exact non-target response identity, all negative fixtures passing, and overhead within limits. That result admits resuming the already-prepared c64 concurrency project for the adapter-enabled endpoint. Any unsafe/ambiguous transformation, non-target mutation, scorer failure, or overhead miss closes this adapter and leaves the economic FP8 result non-production-eligible.
