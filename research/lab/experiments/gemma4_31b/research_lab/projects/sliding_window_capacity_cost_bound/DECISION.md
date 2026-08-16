# Decision — 768-token local-window capacity candidate

The deterministic bound nominates exactly one future candidate: a **768-token
local-attention window**, and only behind matched quality and endpoint-memory
gates. It is the smallest proposed change that crosses the logical BF16-KV c8
peak-residency envelope: **44.484 GiB** at 4,214 prompt plus 358 output tokens,
versus **45.266 GiB** for the 1,024-token control and a **44.704 GiB** usable
L40S envelope. The unchanged non-KV allowance is 39.350 GiB.

This is a capacity discontinuity, not a performance result. The maximum
whole-request effect from QK/AV work is only **0.5440%** at 768 tokens. Even
the 256-token case reaches just **1.7455%**, after retaining the exact
attention projections, MLPs, and required vocabulary sampling in the
denominator. No window clears the campaign's 5% relevance threshold by this
mechanism, and no requests/s, endpoint-cost, or quality claim follows.

512 and 256 tokens are not nominated: they buy more headroom but impose more
context loss without a second relevant capacity tier or a 5% work path.

Before 768 can be credible, evaluate paired 1,024/768 checkpoints on
long-context items whose evidence lies 769–1,024 tokens back, multi-turn
agent/tool traces, the 4,214/358 primary slice, and a 10K slice. Preserve raw
outputs and score quality/feature regressions before matched server-memory and
cost measurement. This packet creates no retained-session arm and did not
inspect or alter the live owner.

`WINDOW_BOUND.json` is the reproducible numerical artifact. It also records
that the source-stated FP8 per-token-head byte formula yields 0.363423 GiB per
primary request, whereas the already scheduled FP8-KV arm reports 0.558736
GiB. That inconsistency is recorded for later reconciliation only; this project
does not modify or weaken that arm's existing gates.
