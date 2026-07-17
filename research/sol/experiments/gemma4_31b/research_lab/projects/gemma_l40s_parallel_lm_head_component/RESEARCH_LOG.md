# Research log

## 2026-07-17 — director delegation

Activated as the sole paid lane after the W4 consumer terminal failed its final gate without a second allocation. Measure actual pinned-image BF16 `ParallelLMHead` at M=1/2/4/8/16/32 and translate 358-step timing into per-request planning/conservative budgets. Because image setup dominates, prepare one official-assistant MTP proposer component while the owner runs and execute it only on the named head-pass/economic/start-ready trigger. Budgets are 90 wall minutes, 20 provider minutes, 0.34 L40S-hours, 3 CPU-hours, one 100-GiB disk, 20 GiB temporary/4 GiB artifacts, and `$0.50`.

## 2026-07-17 — exact-image audit passed; one owner stopped at unobservable provider create

Question: can the actual pinned-image tied BF16 `ParallelLMHead` sweep run under the admitted single shared L40S owner?

Action: replaced the inherited incomplete head prior with a six-row M=1/2/4/8/16/32 staged program. The final exact-image audit passed with CPU/meta construction after TP=1 initialization, binding vLLM `0.19.1.dev6+g6d4a8e6d2`, `vllm.model_executor.layers.vocab_parallel_embedding.ParallelLMHead` (source `5cdb…85494`), and `UnquantizedEmbeddingMethod` (source `3067…f1c92`), BF16 `[262144, 5376]` weight. It also verifies output-consuming CUDA/wall timing, allocator/telemetry fields, 358-step budget translation, internal manifest/stage terminal, and shared durable owner. The official-assistant packet was prepared but not admitted to the owner: it binds a distinct H100/image identity, so it is not start-ready for this exact L40S image.

Evidence: the single `gemma-l40s-parallel-lm-head-20260717T063711Z.service` owner started with a 1,200-second deadline, then its provider create subprocess returned exit 3 before an instance ID or watchdog existed. The controller wrote no create stdout/stderr, so its response cannot be classified as a provider rejection/capacity result. `artifacts/l40s-parallel-lm-head-20260717T063711Z/typed-terminal.json` records this typed observability failure, 0.838 seconds / derived `$0.000176721` exposure, cleanup pass, and authenticated empty instances/disks.

Interpretation and next move: no GPU work, timing row, or economics evidence was produced; do not infer an L40S or `ParallelLMHead` failure. This project has consumed its one owner launch. A future separately authorized retry must first make the named shared controller retain a redacted create diagnostic, then rerun the final audit and owner under a fresh admission.
