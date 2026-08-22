# Gemma 4 inference blog evidence ledger

## Question and decision

Question: what is the strongest technically interesting, externally readable
account of the Gemma 4 31B campaign that can be supported by the repository's
actual measurements?

Decision: publish one deep post rather than five shallow posts. Use the MTP
paradox—4,880 accepted drafts and an 89.86% endpoint regression—as the narrative
spine, then explain why runtime FP8, architecture-specific cache layout, and
decode-equivalent NGRAM survived. Use hardware placement and failed hypotheses
to make the full-stack search concrete. Keep unverified mechanisms in a short,
explicitly labeled forward-looking section.

## Claim scope

- Exact model: `google/gemma-4-31B-it` revision
  `b9ea41a2887d8607f594846523f94c6cc75ac8a4`.
- Main performance scope: one H200, TP1, text-only non-reasoning, 32 concurrent
  complete requests, 4,214 prompt and 358 completion tokens/request, 12.695776%
  prompt-cache reads.
- Primary metric: batch wall time divided by 32.
- Final NGRAM quality scope: same-stack sequential AR/NGRAM GPQA-Diamond-198
  and TauBench-165 captures.
- Non-scope: universal Gemma performance, vision/audio/reasoning, multi-node,
  broad quality parity, a public-provider leaderboard, production reliability,
  or a current market-price claim.

Falsification rule: any headline number without a scope-matched complete-request
terminal is removed or relabeled. Any unmeasured candidate described as a
result fails review.

## Internal evidence map

| Draft claim | Evidence class | Repository anchor |
| --- | --- | --- |
| Workload, stock 0.969888, dynamic chunking 0.930607 and 4.05% | measured endpoint | `projects/gemma4_background_serving_frontier/RESEARCH_LOG.md` and `artifacts/exact-mix-c32-20260718t1729z/` |
| Fused QK norm/RoPE canonical 0.919457 and +1.198% | measured endpoint | `projects/gemma4_h200_fused_qk_norm_rope_endpoint/artifacts/fused-qk-norm-rope-c32-canonical-20260718t1817z/TERMINAL.json`; director log line 686 |
| In-memory FP8 0.748553 | measured endpoint | `projects/gemma4_h200_inmemory_fp8_endpoint/STATUS.json` |
| v0.5.13 dynamic FP8 0.697924 vs 0.928040 | measured endpoint | `projects/gemma4_h200_v0513_fp8_production_validation/PROJECT.md`; director log line 922 |
| QKV 0.700445 to 0.692842, 1.085% | measured paired endpoint | `projects/gemma4_h200_qkv_epilogue_fusion/STATUS.json` |
| Deferred local KV commit +0.26599% retained | measured endpoint | `projects/gemma4_h200_v0513_fp8_qkv_residual_profile/STATUS.json` |
| Global attention 255 registers/thread and BLOCK_M regression | measured profiler + endpoint | `projects/gemma4_h200_v0513_fp8_qkv_residual_profile/STATUS.json` |
| Contiguous local ring 0.676646 to 0.655657, 3.102% | measured paired endpoint | `projects/gemma4_h200_swa_contiguous_ring_cache/STATUS.json` |
| Tied head component and 0.655657 to 0.651828, 0.584% | measured component + endpoint | `projects/gemma4_h200_fp8_tied_head_endpoint/RESEARCH_LOG.md` |
| MTP 4,880 accepted drafts and 0.674326 to 1.280270 | measured endpoint | `projects/sglang_v0512_h200_gemma4_mtp_endpoint/RESEARCH_LOG.md` |
| Initial NGRAM 0.702239 to 0.596751 | measured paired endpoint, not promoted | director log line 1182 |
| Decode-equivalent NGRAM 0.625149 and semantic gate | measured endpoint | director log lines 1541-1590; `projects/gemma4_h200_ngram_decode_equivalent_production_validation/PROJECT.md` |
| AR/NGRAM GPQA 55/198, Tau 10/165, completion tokens, latency | measured quality | `projects/gemma4_h200_ngram_decode_equivalent_production_validation/RESEARCH_LOG.md` |
| BF16/FP8 quality caveat | measured quality with wide uncertainty | `projects/gemma4_h200_v0513_fp8_production_validation/STATUS.json` and `RESEARCH_LOG.md` |
| H100 0.951014 and placement miss | measured endpoint | `projects/gemma4_h100_v0513_fp8_qkv_endpoint/STATUS.json` |
| B200 0.734228/0.633996 and price-normalized miss | measured endpoint + analytical economics | `projects/gemma4_b200_dynamic_fp8_endpoint/STATUS.json` |
| L40S 47.450096 GiB lower bound vs 44.988281 GiB | analytical fit bound | `projects/gemma4_l40s_current_runtime_fp8_endpoint_rebase/STATUS.json` |
| W4 MLP 48.05% fewer bytes but 8.51% slower | measured component | `projects/gemma4_h200_mlp_w4_fp8_hybrid/STATUS.json` |
| Cross-operator target-verification producer | source-complete/CPU-exact candidate | `projects/gemma4_target_verify_crossop_persistent_executor/STATUS.json` |
| GELU-multiply/FP8 fusion bytes and endpoint ceiling | source-complete/CPU-exact candidate | `projects/gemma4_h200_gelu_mul_fp8_quant_fusion/STATUS.json` |
| Prompt-state compaction 4,214 to 1,152 and 0.498701 bound | derived, quality-unvalidated | `projects/gemma4_prompt_token_compaction_codesign/STATUS.json` |

All paths above are relative to
`research/sol/experiments/gemma4_31b/research_lab/`.

## Public source table

Retrieved 2026-08-03 and refreshed 2026-08-04. Technical browsing used primary sources except for
Wafer's own posts, which were reviewed only as first-party style examples.

| Source | Publication/revision | Evidence type | Use |
| --- | --- | --- | --- |
| [Gemma 4 model overview](https://ai.google.dev/gemma/docs/core) | Google, retrieved 2026-08-03 | vendor-reported primary | model-family context |
| [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4) | Google, retrieved 2026-08-03 | vendor-reported primary | modalities and context scope |
| [Gemma 4 31B config](https://huggingface.co/google/gemma-4-31B-it/blob/main/config.json) | checkpoint main, retrieved 2026-08-03 | source identity | exact 31B layer, head, window, vocabulary geometry |
| [Transformers Gemma 4 configuration](https://github.com/huggingface/transformers/blob/main/src/transformers/models/gemma4/configuration_gemma4.py) | main, retrieved 2026-08-03 | official source | configuration semantics |
| [Transformers Gemma 4 model](https://github.com/huggingface/transformers/blob/main/src/transformers/models/gemma4/modeling_gemma4.py) | main, retrieved 2026-08-03 | official source | output-head and attention implementation context |
| [SGLang server arguments](https://github.com/sgl-project/sglang/blob/main/docs/advanced_features/server_arguments.md) | main, retrieved 2026-08-03 | official documentation | NGRAM runtime controls |
| [Google Gemma 4 MTP overview](https://ai.google.dev/gemma/docs/mtp/overview) | Google, retrieved 2026-08-03 | vendor-reported primary | MTP context only; no performance transferred |
| [Wafer: Qwen3.6 on MI355X](https://www.wafer.ai/blog/qwen36-mi355x) | 2026-05-11 | first-party style example | headline/workload/method/economics structure |
| [Wafer: Heterogeneous compute one kernel at a time](https://www.wafer.ai/blog/kernels-are-still-the-moat) | 2026-05-19 | first-party style example | deep mechanism, diagram, and production-gate structure |
| [Wafer: Performance per dollar](https://www.wafer.ai/blog/glm52-amd) | 2026-07-03 | first-party style example | hardware economics and negative framework selection |
| [Wafer: The inference alpha](https://www.wafer.ai/blog/inference-alpha-amd) | 2026-06-10 | first-party style example | full-stack framing; not used for technical claims |
| [Wafer: Where Did My Microseconds Go?](https://www.wafer.ai/blog/where-did-my-microseconds-go) | 2026-03-17 | first-party style example | anomaly-led opening, forensic progression, exact fix |
| [Wafer: Reward hacking field guide](https://www.wafer.ai/blog/reward-hacks-field-guide) | 2026-03-12 | first-party style example | sharp stakes, concrete failure taxonomy, terse defenses |
| [Modal: Host overhead is killing your inference efficiency](https://modal.com/blog/host-overhead-inference-efficiency) | 2025-11-18 | first-party style example | memorable systems invariant followed by trace-level evidence |
| [vLLM: PagedAttention](https://vllm.ai/blog/2023-06-20-vllm) | 2023-06-20 | first-party technical/style example | one physical analogy carried from memory problem to implementation |
| [Baseten: DFlash](https://www.baseten.co/blog/dflash-faster-llm-inference/) | 2026-05-08 | first-party style example | mechanism and measured result introduced together |
| [Baseten: Fastest GLM-5 API](https://www.baseten.co/blog/how-we-built-the-fastest-glm-5-api/) | 2026-03-06 | first-party style example | architecture-specific mechanism order and low-overhead speculation framing |

## Style synthesis

The useful conventions were structural, not textual:

1. lead with a scoped number and workload;
2. show enough model geometry to motivate the optimization;
3. explain a small number of mechanisms at the kernel/dataflow level;
4. separate single-stream, aggregate, and economic denominators;
5. include quality and production-readiness evidence;
6. let a benchmark anomaly or failed intuition create narrative tension;
7. finish with a direct systems thesis rather than a generic product summary.

The revision removed the numbered “Optimization 1/2/3/4” report structure,
opened on the failed MTP result, reduced evidence terminology in the main flow,
and made the section titles state physical claims (“A local window is a queue,
not a database”) rather than categories. It also cut generic connective phrases
and retained exact shapes, counters, and A/B denominators. No source wording,
diagram, or unpublished claim is reproduced.

## Uncertainty and competing explanations

- The milestone progression combines retained endpoints from the campaign; not
  every adjacent point is a clean isolated A/B. The article explicitly says so
  and gives paired controls for claimed intervention effects.
- Dynamic FP8 versus BF16 quality is not proven equivalent. TauBench's paired
  interval is wide. The draft reports the interval and limits NGRAM promotion
  to the same FP8 stack.
- The final 0.625149 endpoint differs from the control on whitespace formatting
  for one tool-call row, though parsed semantics match. Output-token accounting
  is reported.
- Quality-suite absolute scores are low. They are used for paired regression
  evidence, not a claim that the endpoint is generally strong at those tasks.
- Provider prices change. The article reports placement decisions and misses,
  not time-sensitive hourly prices or a current cheapest-provider claim.
- Some campaign experiments contain operational failures. Only scientific
  terminals identified above enter performance claims.
- The three “next bets” are not measured endpoint results. Their evidence class
  appears in each heading.

## Reproduction and review

No new experiment was run for the article. Reproduce claims by opening the
anchors above and verifying the immutable terminal hashes recorded in their
project logs/status files. Review the draft with:

```sh
python3 tools/devex/check.py
python3 research/sol/docs/blog/gemma4-inference-optimization/verify_blog.py
git diff --check -- research/sol/docs/blog/gemma4-inference-optimization
```
