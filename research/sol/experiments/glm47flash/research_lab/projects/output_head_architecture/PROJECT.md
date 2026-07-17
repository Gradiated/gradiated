# Output-head architecture cost proxy

## Question

Can a recoverable modification to GLM-4.7 Flash's unusually large output head reduce serving cost materially on the c16 L40S frontier?

## Why this is an independent lane

The model maps a 2,048-wide hidden state to a 154,880-token untied vocabulary. Retained traces attribute about 14.1% of the observed c8 decode interval union to the BF16 vocabulary projection. The public AWQ checkpoint explicitly leaves `lm_head` unquantized. A lower-rank factorization, adaptive/hierarchical vocabulary, dynamic shortlist, or another model-supported construction could reduce this work; unlike a hand-tuned equivalent kernel, it may change the architecture and be recovered through post-training.

## Research scope

Bind the exact LM-head weights and current serving shapes. Measure singular spectrum, token/vocabulary usage where available, theoretical bytes/FLOPs, exact-shape component behavior, and the maximum endpoint transfer consistent with current telemetry. Build the cheapest faithful runtime or tensor proxy for one or more promising constructions, such as low-rank factorization or a two-stage shortlist. Explain how the construction maps to L40S versus bandwidth-richer H100/AMD parts and whether it changes memory placement enough to alter the best production chip.

Do not begin with broad quality evaluation or full retraining. Semantic changes are allowed during this discovery proxy and must be labeled. The output should be a measured/bounded cost opportunity, an implementation path, and the post-training recovery burden—not merely a literature list.

## Resources and constraints

- Current c16 control: 535.286 output tok/s at committed-planning COGS of about $0.571/M output-equivalent.
- Exact BF16 and AWQ checkpoint files are locally cached.
- Retained c8 trace analysis is under `moe_dense_residual`; refresh the relevant shape at c16 only if it can change the decision.
- Use committed production prices for the economic headline.

## Decision

Promote a construction only if its component evidence supports at least a 10% sustainable endpoint-cost path from the committed-price c16 denominator (about $0.571/M to at most $0.514/M output-equivalent), or an equally material cheaper-chip placement, enough to justify post-training and a full c16 server experiment. Otherwise close the output-head architecture lane and return capacity to MoE, depth, MLA-rank, or draft-head changes.
