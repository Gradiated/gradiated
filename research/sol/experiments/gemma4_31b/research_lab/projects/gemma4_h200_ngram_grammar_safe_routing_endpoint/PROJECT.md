# Grammar-safe native NGRAM routing

## Question

Can SGLang native NGRAM remain enabled for ordinary completion traffic while
grammar-bearing and tool requests are routed through exact autoregressive target
decoding, preserving production features and the measured no-grammar c32 gain?

## Why this matters

The unchanged native NGRAM endpoint measured `0.5967508053 s/request` versus
`0.7022385985` for its matched control, a 15.02% reduction below the campaign's
`0.6381105231 s/request` H200 ceiling. Its final server-boundary trace closed
production promotion for one precise reason: the single-tool request generated
41 whitespace-expanded tokens instead of the control's 24 compact-JSON tokens.
The other nine deterministic rows, including multi-tool, were token exact.

The campaign c32 workload is a raw completion workload with no tools, response
format, or grammar. A request-class policy can therefore preserve NGRAM on the
economic workload while removing speculation from the feature class where the
measured divergence occurred.

## Bound intervention

Consume `DIRECTOR_BINDING.json`. Preserve the exact checkpoint, tokenizer,
SGLang v0.5.13 image and commit, dynamic-FP8/QKV/KV stack, native NGRAM
proposal contract, c32 workload, sampling, and native Gemma tool parser.

Implement one source-level routing rule at the scheduler/speculative boundary:

- batches or requests carrying grammar-constrained structured generation,
  including native tool-call requests, must use ordinary target autoregressive
  generation and must show zero NGRAM proposal/verification activity;
- requests without grammar constraints must follow the unchanged native NGRAM
  path and must show real proposal, target verification, and acceptance;
- a mixed batch may conservatively fall back in full when the pinned scheduler
  cannot separate request classes without changing batching semantics.

Do not canonicalize generated text, alter completion accounting, rewrite tool
payloads, tune NGRAM, or special-case the frozen prompts.

## Experiment

Prepare the routing patch and reuse the proven token-trace and endpoint
launchers project-locally. After the renewed reservation is durable, claim
empty bench `h200-sync-linear-e00vhh6h29fj68x91g` and run two sequential
servers:

1. One matched non-speculative control runs the frozen ten-row deterministic
   text/tool suite and exact 32-request c32 workload, persisting server-boundary
   token IDs, normalized API payloads, accounting, and endpoint rows.
2. Remove the control and prove zero compute processes and zero HBM. Start the
   grammar-safe routed candidate and run the byte-identical suite and c32
   workload once.

The candidate passes only with:

- 10/10 exact scheduler and emitted token sequences, normalized text/tool
  payloads, finish reasons, and completion accounting;
- zero speculative activity for grammar/tool rows and real NGRAM
  proposal/verification/acceptance for ordinary rows;
- 32/32 exact c32 generated-token sequences, finite rows, exact prompt/cache
  accounting, and sane outputs;
- candidate service time at or below `0.6381105231 s/request`.

A complete pass qualifies the routed endpoint and permits transfer of the
already-bound FP8 GPQA-Diamond, TauBench, NLL, and tool-consumer evidence. Any
tool-path speculation, generated-token mismatch, or endpoint miss closes this
routing hypothesis.

## Resources and limits

- Profile: `execution`.
- Spend: at most `$8.00`.
- Compute: at most 90 claimed H200 minutes.
- Wall clock: at most 150 minutes from researcher start.
- Storage: at most 8 GiB of new project-local artifacts.
- Provider mutation is forbidden.

The active DFlash project and its independent H200 are out of scope. Do not
wait for, inspect, restart, or modify that owner.

## Director disposition — 2026-07-24

The routed candidate is terminal. The tool-route guard did not observe native
tool requests at `Req.grammar`, but that integration defect is no longer worth
repairing: the persisted post-generation traces prove that the ordinary
no-grammar c32 candidate differs from its matched target-only control on 31 of
32 complete generated-token sequences, including when compared as unordered
multisets after excluding warmup. This violates the project's exact-token gate
independently of tool routing. `DIRECTOR_C32_TRACE_DISPOSITION.json` binds the
trace hashes and comparison. Do not reopen native NGRAM.
