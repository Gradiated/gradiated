# Adaptive top-2/shared router observer gate

## Question

Can the exact pinned GLM/vLLM runtime accumulate a router-confidence qualification histogram asynchronously on device, without synchronizing or materially perturbing the measured top-2/shared performance opportunity?

## Why it matters

Unconditional top-2/shared measured `666.860853` tok/s versus `611.764559` for top-4/shared, an `8.262%` wall-time reduction. A zero-overhead adaptive policy needs only about `35.253%` of token-layer decisions on top-2 to produce a 3% throughput gain, materially below the terminal top-2/no-shared project's `74.918%` requirement. The candidate's truncated quality response makes confidence-adaptive routing scientifically relevant, but no exact router-margin distribution is retained.

## Evidence

- `../full47_top2_shared_c32_direct_corrected/` for exact top-4/top-2 performance and identities.
- `../adaptive_moe_budget_bound/` for the source-bound policy fixture and prior absence result.
- `../exact_router_geometry_recovery/` for the archive-level route-evidence close.
- Pinned runtime source under `/root/workspace/research/lab/experiments/glm47flash/campaign_100` and the exact local checkpoint config.

## Scope

Work at `$0` and source-only. Do not run the model, use CUDA/provider resources, edit the shared runtime, stage a launcher, collect an observer trace, train a gate, or prepare an endpoint. Trace the exact router/logit/top-k call path and decide whether a fixed-size device histogram of a source-defined confidence statistic can be updated without `.item()`, CPU transfer, device synchronization, dynamic allocation, or per-token logging in the timed path. Bind all source/config identities.

Recompute the qualification/observer-overhead curve from the measured `8.262%` wall-time ceiling. Return `OBSERVER_SOURCE_PASS` only if the statistic and update point are exact, the hot-path operation is bounded and non-synchronizing by construction, and a deferred bulk read could test the roughly `35.253%` qualification boundary with enough overhead margin to preserve a 3% endpoint opportunity. Otherwise close. A pass nominates only a later observer decision; it is not authority to implement or run one.

## What changes the portfolio

A source pass makes adaptive top-2/shared the leading quality-aware successor to the measured unconditional proxy. A failure closes adaptive routing without provider spend and leaves the unbracketed global top-2 signal for future recovery consideration only.

## Available resources

- `/root/workspace/research/factory/tools`
- `/root/workspace/research/lab/experiments/glm47flash/campaign_100`
