# Post-L40S-FP8 successor selection

## Decision question

After valid direct raw CUTLASS FP8 linears close both L40S c12 economic envelopes, what is the single shortest runnable paid experiment most likely to create a material margin over the campaign frontier?

This is a `$0` cross-portfolio ranking project. It must not poll or mutate provider state, invoke GPU/image/checkpoint/compilation, edit other projects, or create a launcher. It returns one already-supported paid experiment contract or typed none; no readiness chain.

## Evidence and scope

Treat the following as controlling:

- direct L40S conditional stage: 12/12 exact rows pass; linear floor `1.9266673329410453 s/request`; plus independent attention/KV residual `0.1646315388888889` gives `2.091298871829934`, above planning `1.3945806410831811` and conservative `0.8632931049626701`; endpoint/head/service costs are omitted;
- RTX 6000 Ada transfer gate remains conditional and cannot inherit throughput or admission;
- W4 producer/quality, queue, price, and synthetic-bound projects;
- H100 hardware/kernel frontier and the concurrently active H100 hybrid-attention mechanism project, without waiting for or editing it;
- H200 BF16 c32 component/prefill/attention evidence and invalid endpoint lineages;
- MI355X, B200, SGLang, MTP, cache, tied-head, sparse/low-rank, and full-stack alternative terminals.

Rank at most four materially different candidates by expected whole-request cost margin, information value, implementation/runtime support, checkpoint/setup burden, experimental spend, and time to a valid result. Search across project boundaries. Reject any candidate that needs another source/readiness gate before GPU, transfers the L40S FP8 result across hardware, relies on the invalid oracle, or cannot plausibly improve whole-request economics by 5%.

Return exactly one of:

- a named next paid component/endpoint arm with exact first scientific rows, matched comparator if needed, authoritative local inputs, proven lifecycle, mechanical identity fields, wall/provider/compute/storage/spend caps, stop rule, and one optional adjacent retained-session trigger; or
- `typed_none_wait_for_h100_mechanism` if no independent candidate is executable without that active mechanism result.

Do not activate or create the paid project. Write `SELECTION.json`, update log/status, terminalize.

## Budgets

- Wall clock: 25 minutes.
- Compute: 2 local CPU-hours; no GPU.
- Storage: 384 MiB retained plus 128 MiB temporary.
- Spend: `$0`; no provider, image, checkpoint, compilation, or external mutation.
