# H100 v0.5.15 depth-aware NGRAM representation

## Question

Can the exact v0.5.15 native-NGRAM path represent a load-adaptive draft depth
end to end—producer, target rows, attention metadata, acceptance, KV movement,
and CUDA-graph shape—without the layout corruption that invalidated the prior
H200 depth-6 arm?

## Why it matters

Measured NGRAM acceptance falls from 11.876 drafts at 1–7 running requests to
about 5.2 drafts at eight or more, while depth 12 continues to verify all
rows. The prior H200 implementation was a valid negative for its exact patch,
but it shortened only the consumer-facing depth while the corpus producer
remained fixed at 12. That produced divergent target rows and an illegal
memory access; it does not establish that a coherent depth-aware
representation is impossible on the exact H100 v0.5.15 stack.

## Scope

Use only the bound v0.5.15 source, measured H100 endpoint telemetry, and the
prior H200 negative artifact. Reconstruct every shape and ownership invariant,
then either prepare one source-complete depth-aware representation with a
fail-closed CPU/state oracle and quantitative work bound, or close the lineage
with a source-proven infeasibility. Do not use a GPU or provider, inspect the
independent packed-mask project, sweep depth or thresholds, or infer endpoint
performance.

The exact contract is frozen in `DIRECTOR_BINDING.json`.
