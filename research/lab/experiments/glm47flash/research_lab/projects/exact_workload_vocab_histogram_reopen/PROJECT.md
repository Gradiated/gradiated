# Exact-workload vocabulary-histogram reopen gate

## Question

Do the first complete order-free output-token histograms from the authoritative 8,192-input/1,024-output current-AWQ workload provide representative evidence for an output-vocabulary shortlist, or do their concentration, repetition, speculative method, or missing order keep the output-head lane closed?

## Why this matters

`workload_vocab_shortlist_gate` closed because the retained stock performance archives contained counts and hashes but no token identities. The terminal n-gram arm now contributes 32 request-complete histograms totaling 32,768 target-model output tokens. This is genuinely new `$0` evidence collected on the exact performance geometry, but it must not be promoted automatically: the visible rows are dominated by one token and repeat nearly identical histograms, and the source arm used prompt-lookup speculation. A fast corpus adjudication can either close this reopen condition durably or identify a small, testable output-head proxy without sharing the live depth-42 provider owner.

## Fixed evidence

- Primary archive: `../ngram_speculative_c16_direct/artifacts/ngram_speculative_c16_direct_2026-07-16-r1/summary.json` and its authenticated batch archive, SHA-256 `b1a2381cb414a424bddcc3ce2a2b4fc234e397a154616fd15691ea8f13c593c7`.
- Source endpoint: 32/32 exact c16 requests, 1,024 output tokens each, complete histograms, target-verified decoding, and semantic/determinism checks passed. Its `90.8004806` tok/s endpoint is a closed speculative-scheduling result, not a performance prior for an output-head intervention.
- Prior gates: `../workload_vocab_shortlist_gate/` and `../output_head_architecture/`, including their corpus, spectrum, tensor-geometry, and economic artifacts. Do not reopen their norm-ranked or low-rank proposals.
- Exact tokenizer/checkpoint identity: current AWQ revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`; decode individual token IDs only with the bound tokenizer. Token order and raw text were intentionally not retained.
- Economics: planning L40S `$1.10/hour`; current valid r3 c16 `552.1710554232396` output tok/s; absolute gate `594.466`; robust nomination gate `606.355`; required non-overlapped wall-time removal `7.1148%`.
- The active `minimal_depth42_v2_l40s_direct` durable owner is out of scope. Do not wait for, inspect, poll, or use its live/terminal artifacts.

## Execution contract

Work offline for at most 600 seconds, 4 GiB RSS, 16 MiB of new artifacts, and `$0`. Verify all request histograms are complete and sum to the reported outputs. Measure aggregate and per-request vocabulary size, token concentration, distinct histogram patterns, batch-half and leave-one-request-out stability, and coverage curves at practical tensor-friendly shortlist sizes. Decode only the retained token IDs needed to identify control/special/repetition artifacts; do not reconstruct or infer token order.

Adjudicate representativeness before economics. Separate the campaign's exact length/concurrency geometry from target-usage diversity, account for repeated synthetic prompts and the n-gram intervention, and fail closed if the corpus is degenerate, duplicated, method-conditioned, or lacks enough independent groups for a leave-one-group-out claim. Stream hashes alone do not prove semantic diversity.

Only if the corpus survives, bind the smallest defensible shortlist to the exact 154,880-by-2,048 BF16 head. Quantify rows, bytes, GEMM shapes, ideal component savings, conservative endpoint transfer, and the runtime/recovery burden. A shortlist is semantics-changing unless an exact executable fallback or routing representation is identified; observed coverage is not exactness. Use the prior 14.09% c8 projection interval only as an optimistic ceiling and require the conservative transfer to reach `606.355`.

Return exactly one terminal result:

- `CORPUS_CLOSE`: completeness fails or the retained histograms are too concentrated, repeated, method-conditioned, biased, or under-grouped to represent target usage;
- `ECONOMIC_CLOSE`: the corpus is adequate, but no exact representation or conservative `606.355` path survives; or
- `NOMINATE_SHORTLIST_PROXY`: target-representative evidence supports at least 99.9% leave-one-independent-group-out coverage, an exact source-bound runtime representation exists, and conservative endpoint transfer reaches `606.355`.

Do not use CUDA, network/provider resources, download data, mutate a checkpoint or shared runtime, build a controller, train, run quality evaluation, or launch a successor. Produce one compact machine-readable decision artifact, an optional focused local analysis script, and a concise research-log update.

## Available resources

Use the fixed local projects above, `/root/workspace/research/factory/tools`, and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.

## Cycle 135 reactivation: method-free stock identities

The completed background-knee archive now supplies the explicit reopen evidence absent before: five unchanged-stock, non-speculative profiles with complete output-token histograms. They contain `292` request-complete rows, `299,008` output tokens, and `292` distinct stream hashes across c24/c28/c30/c32-pre/c32-post. Token `154822` still contributes `278,264` tokens (`93.06%`), so this evidence may reveal workload degeneracy rather than a shortlist opportunity.

Re-run this same project once at `$0`, within 900 seconds, 4 GiB RSS, and 32 MiB new artifacts. Verify archive SHA-256 `94e2f841e3a0aa1b4c166e4a4defa20e2b3c5b0cd2ab23f9acc7877ae4d86dbf`; compare the five stock profiles with the prior n-gram group; deduplicate hashes; measure per-profile/leave-one-profile coverage at tensor-friendly shortlist sizes; and decide explicitly whether concurrency profiles constitute independent target-usage groups. Fail closed if they do not. Do not infer semantic diversity from unique stream hashes or exact geometry.

Only if representativeness survives, require an exact source-bound shortlist/fallback representation that avoids the full head without answer leakage, at least `99.9%` leave-one-group-out coverage, and a conservative endpoint path to both `606.355` tok/s and `1.03x` the new `602.157121` control mean. Return one terminal `CORPUS_CLOSE`, `ECONOMIC_CLOSE`, or `NOMINATE_SHORTLIST_PROXY`; do not prepare CUDA, a checkpoint, runtime integration, training, quality work, or provider execution.
