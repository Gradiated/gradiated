# Endpoint-overflow reconciliation — 2026-07-25

Decision: **reject for deployment; retain only as analytical, semantic-blocked
economics.** The endpoint's normalized semantics diverged at request 277, so
neither H100-only nor H100-plus-retail scheduling is production eligible.

All six bound files hash-match and the old 0.707333994-second finite one-H100
control reproduces exactly. The measured 791-request endpoint rate is
0.780757973 seconds/request, not transferable as measurement beyond its exact
prefix.

On the measured 791-request prefix, one H100 finite buffering reaches 68.057
seconds maximum FIFO wait. Repeating that prefix grows to a 4,405.604-second
drain extension after 64 periods, so finite buffering is not sustainable. At a
one-second local wait cap, the periodic greedy-minimum policy spills 88
requests and costs `$0.133066/M` at the capability-listed tier and `$0.133369/M`
at methodology-matched retail: below `$0.135281/M` and `$0.138/M`, but above
the `$0.119/M` nominal tier. The continuous 90%-utilization H100 cost is the
measured `$0.147579/M`; two-H100 finite cost is `$0.236368/M`.

The 1,036-request result is explicitly an extrapolation: it reaches 89.163
seconds finite maximum wait and a 5,756.403-second 64-period extension. A
one-second cap spills 115 requests per period at `$0.133068/M`
capability-listed and `$0.133370/M` methodology-matched. It likewise misses
nominal retail. Retail-only, no-spill H100-only, and all raw caps—including
five seconds—remain separately recorded in the dated JSON frontier.

No provider, GPU, SSH, or endpoint replay occurred. The semantic blocker must
be repaired before any scheduling result may be promoted.
