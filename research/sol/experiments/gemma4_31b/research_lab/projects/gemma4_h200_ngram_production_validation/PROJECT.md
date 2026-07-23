# Native n-gram production validation

## Question

Does the exact SGLang v0.5.13 native n-gram endpoint preserve the served model's deterministic text and required tool behavior closely enough to qualify its measured `0.5967508053 s/request` result as the production frontier?

## Why this matters

The frozen native n-gram contract is the first exact H200 arm to beat the campaign ceiling: `0.5967508053 s/request` versus a contemporaneous `0.7022385985` control, a measured 15.02% gain. It used the exact checkpoint, workload, FP8/QKV/current simple-gain stack, 32/32 requests, exact prompt-cache accounting, and no assistant model.

That performance result deserves the campaign's deferred quality gate. The pair did not return token IDs, and a director-side preliminary reconstruction of the persisted SSE text found 19/32 control/candidate differences despite `temperature=0` and the same seed. This may be a streaming representation issue, scheduling-sensitive numerical behavior, or real output divergence; it must be resolved before production promotion. The prior exact v0.5.13 FP8 production validation remains useful only after the n-gram execution semantics and served feature path are bound.

## Bound scope

`EVIDENCE_BINDING.json` mechanically binds the exact checkpoint, model revision, image/runtime, native n-gram contract, workload runner, performance terminals, preliminary response screen, and prior quality consumer. Preserve:

- `google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4`;
- SGLang v0.5.13 image digest `6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6`;
- the frozen native `NGRAM` contract: 12 draft tokens, BFS breadth 1 through 10, trie capacity 10,000,000, maximum match window 18, no assistant model, overlap disabled, and mixed chunking disabled;
- the exact dynamic-FP8, fused-QKV, deferred-local-KV, dense-add, producer-fused metadata stack and read-only resident checkpoint;
- the exact deterministic request identities and native Gemma tool parser.

Do not tune n-gram settings, change sampling or workload geometry, add an assistant, alter checkpoint/runtime bytes, or turn this into another performance sweep.

## Experiment

Start with the persisted pair and no GPU:

1. Normalize every SSE response through one explicit consumer that distinguishes incremental text chunks, cumulative text, usage-only events, and `[DONE]`. Recover generated token IDs from bound tokenizer bytes when possible. Explain the preliminary 19/32 text differences and persist per-request control/candidate text and token hashes.
2. Inspect the pinned n-gram proposal/verification path just enough to state whether only target-verified tokens can reach the response stream. Bind the exact source symbols and reject any fallback or unverifiable path.

After the `$8.00` reservation is durable, atomically claim `h200-sync-linear-e00vhh6h29fj68x91g`. Preserve and inspect the healthy `gemma-ngram-pair` server before any restart. Run one hash-bound deterministic equivalence and feature suite against native n-gram and a matched non-speculative control, requiring:

- exact generated token identity for ordinary text, stop/length, cached-prefix, and repeated-pattern cases;
- stable results across a minimal serial and batched discriminator;
- native Gemma single- and multi-tool calls with exact tool names/arguments, `finish_reason`, usage, and parser identity;
- real n-gram path and target-verification proof, with no assistant execution.

If the exact token and feature gates pass, combine that source/path evidence with the already-bound v0.5.13 FP8 GPQA-Diamond, TauBench, NLL, and native tool-consumer terminal; do not regenerate broad benchmark captures. If any generated-token or tool gate fails, production promotion remains blocked. In that case run only the smallest hash-bound candidate-side GPQA-Diamond/TauBench raw capture needed by the existing normalizer/scorer to determine whether the divergence is materially harmful; do not replay a matched performance pair or sweep settings.

## Resources and limits

- Bench: retained `h200-sync-linear-e00vhh6h29fj68x91g`, ahead of the local-window proxy while the n-gram server is warm.
- Spend: `$8.00`.
- Compute: at most 75 claimed H200 minutes.
- Wall clock: at most 150 minutes from first researcher start.
- Storage: at most 8 GiB of new project-local artifacts.
- Provider mutation is forbidden; use the director-registered bench and release it ready.

## Decision

Promote `0.5967508053 s/request` as the quality-qualified production frontier only if target-verification semantics, exact deterministic token equivalence, and required native tool behavior pass. A failure keeps the throughput measurement as a quality-unqualified experimental result and closes unchanged native n-gram for production unless the bounded benchmark discriminator shows no material quality loss and identifies a credible recovery. Preserve all negative evidence.

## Director continuation — sequential servers on an empty H200

The prior validation did not test NGRAM semantics. The read-only checkpoint
repair reached exact FP8 model construction, but the control OOMed because the
healthy candidate still occupied all but 54 MiB of HBM. No control reached
`/v1/models`, no candidate request was submitted, and the token/tool and
conditional quality consumers remain unstarted.

Consume `DIRECTOR_SEQUENTIAL_SERVER_VALIDATION.json` under renewed `$12`
authority. On the director-cleaned H200, run the exact non-speculative control
suite first and persist raw response events, server-side generated token IDs,
usage, finish reasons, and native parser outputs. Stop and remove that server
and require zero accelerator processes and zero used HBM. Only then start the
frozen native NGRAM candidate and run the byte-identical suite once. Concurrent
control/candidate residency is prohibited.

Require exact deterministic generated-token identity across ordinary text,
forced stop/length, cached-prefix, repeated-pattern, serial/batched, and native
single- and multi-tool cases; also require target-verification path proof and no
assistant execution. Exact equivalence authorizes transfer of the bound
v0.5.13 FP8 GPQA-Diamond, TauBench, NLL, and tool-consumer evidence. If
equivalence fails, run only the smallest candidate-side GPQA-Diamond/TauBench
raw capture through the existing bound normalizer/scorer. Do not replay the
performance pair, tune NGRAM, add an assistant or corpus, or change checkpoint,
runtime, precision, sampling, workload, or parser bytes.
