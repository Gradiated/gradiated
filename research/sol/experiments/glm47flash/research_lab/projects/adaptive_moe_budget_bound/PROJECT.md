# Confidence-adaptive MoE budget bound

## Question

Can a token-adaptive policy preserve the stock top-4-plus-shared MoE path for uncertain tokens while sending sufficiently confident tokens through a top-2/no-shared path to clear the campaign's 9.955% wall-time reduction gate?

## Why it matters

The fixed `adaptive_moe_architecture` delivery route is terminally closed, but its retained c16 trace bound remains useful mechanism evidence. Top-2 alone has only a 6.187% ideal trace-resident ceiling and removing the always-on shared expert alone has only 7.101%; applying both universally has a 13.288% ideal ceiling. A dynamic budget is a materially different architecture: it keeps the full path where router confidence is weak and spends less only on qualified tokens. Before any new kernel, training, or provider work, the portfolio needs to know whether exact runtime observability and a plausible qualifying fraction exist.

The campaign gate divided by the combined ideal ceiling implies that at least 74.918% of token-layer decisions must take the cheaper combined path even with zero policy, compaction, or dispatch overhead. This is a hard fail-fast threshold, not a quality claim.

## Scope

At zero provider spend, bind the exact current AWQ config/checkpoint, 46 serving MoE layers, 64 routed experts, stock top-4 normalization and `noaux_tc` routing, the separate always-on shared-expert path, the pinned derived vLLM runtime, and the retained c16/decode trace evidence. Inspect repository-owned artifacts for exact router logits/scores, selected-expert weights, margins, entropy, or per-token grouped-GEMM evidence. Do not infer a distribution from synthetic random routers or unrelated models.

Build the smallest source-bound CPU policy fixture needed to express three conservative cases on the same token-layer decision: stock top-4-plus-shared, top-2 with shared retained, and top-2 with shared skipped. Quantify the minimum qualifying fraction after explicit policy/dispatch overhead sensitivity, whether the current runtime exposes the required statistic without material synchronization, and the minimum observer sample that could falsify the candidate. Treat shared skipping as a new semantics-changing conditional gate; the checkpoint has no learned shared-expert gate.

Do not run a GPU, mutate a provider, edit the shared launcher, integrate the old fixed patch, stage an image, train a gate, create a controller, or claim endpoint/quality transfer. Do not attach work to the active native-MTP session. If no exact router evidence exists, return a typed absence plus one narrowly specified future observer only if its ideal bound can still clear 594.466 output tok/s after conservative overhead; otherwise close the line.

## Resources

- Fixed MoE source and trace evidence: `../adaptive_moe_architecture/`.
- Exact current control: `../nebius_current_awq_c16_direct/`.
- Expert geometry evidence: `../expert_count_geometry/`.
- Checkpoint/config: `/root/.cache/glm47flash-awq-ab31d120`.
- Pinned runtime/launcher source: `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/`.
- Shared tools: `/root/workspace/research/factory/tools` and `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.

## Portfolio-changing result

Return one decision artifact with exact hashes, the policy fixture, required qualifying-fraction/overhead curve, available or absent router evidence, and a close-or-observe recommendation. Nominate at most one later observer—not a candidate endpoint A/B—only if exact current-runtime router statistics are cheaply observable and the conservative bound remains at least 594.466 output tok/s. Any requirement for invented router distributions, universal no-shared/top-2 semantics, a new training campaign, or a second paid owner closes this project.
