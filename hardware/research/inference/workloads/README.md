# Workloads and benchmark protocols

A workload pins input bytes or a dataset manifest, model task, input/output lengths, context, batch/concurrency, decoding, warm-up and quality requirements. Changes create a new version. Training data, development data and final evaluation have distinct roles.

Existing joke-model evaluations are quality checks, not representative conversational benchmarks. Their details remain in the model records. Do not relabel the synthetic 1,000-input evaluation as a general inference performance suite.

For new comparisons, freeze prompts and output limits before measuring and follow the [measurement standard v2](../experiments/measurement-standard-v2.md). Keep TTFT, decode TPS and sustained throughput distinct. Record the electrical boundary of measured energy, including when only module-rail power is available. Preserve the existing baseline and historical three-prompt aggregate. Additional cases receive a new workload identity, with results by case and length. Component benchmarks can isolate arithmetic, memory bandwidth and CPU round trips without restarting the baseline programme.

Cross-chip tests require a common task and quality threshold. Byte-token and subword-token rates are not directly comparable. Report the tokenizer and useful completed work. Equal model names alone do not establish equivalence.

## Prepared milestone suites

The versioned KV260 prompt/context, request-load and repeatability manifests are preparation inputs, not measurements. See the [roadmap](../experiments/benchmark-roadmap.md) and [preparation handoff](../experiments/kv260-milestone-preparation.md) for their protocols, local synthetic checks and execution gates. Keep natural completions, diagnostic score-step replay and offered-load workloads separate. New prompt references are pending inference authorisation. None of these files authorises a board run or changes the frozen model.
