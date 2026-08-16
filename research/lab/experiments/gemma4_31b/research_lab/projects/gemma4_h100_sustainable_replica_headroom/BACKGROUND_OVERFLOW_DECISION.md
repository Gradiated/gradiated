# Background buffering and retail-overflow decision

Decision: **endpoint-dependent nominate** for a one-H100 plus bounded-retail
overflow policy; it is analytical scheduling evidence, not a measured endpoint
or production reliability claim.

The five director-bound inputs all hash-match. The prior two-replica control
also reproduces exactly: 1,036 local requests and a 719.628801-second drain
span at the settled 0.707333994-second service estimate.

One FIFO H100 can absorb the *finite* trace, but only by accumulating a
13.169216-second maximum wait and 13.876550-second drain extension. Repeating
the trace proves that this is not sustainable buffering: drain extension grows
by 13.876550 seconds per period and reaches 888.099228 seconds after 64
periods. The one-H100 average-rate stability ceiling is 0.693940 seconds per
request; the stricter prior 90%-headroom ceiling is 0.624546 seconds.

The sustainable greedy minimum-overflow frontier routes a request to retail
only when its local FIFO wait would exceed the selected cap. At a one-second
cap, the repeating policy spills 20 of 1,036 requests (91,440 tokens) per
period and holds observed local wait below one second. Its planning cost is
`$0.120349/M` at nominal retail, `$0.120663/M` at capability-listed retail,
and `$0.120715/M` at methodology-matched retail. The capability-listed and
methodology-matched points beat their frozen retail tiers (`$0.135281/M` and
`$0.138/M`); the nominal comparison remains `$0.001349/M` above its much lower
`$0.119/M` tier. A 60-second cap spills 19 requests and costs `$0.120234/M`,
`$0.120532/M`, and `$0.120582/M`; it is the lower-cost higher-wait Pareto
point. The zero-wait policy spills 518 requests and is uneconomic.

At the actual `$2.95/h` experimental rate, the one-second policy is
`$0.126673/M`, `$0.126987/M`, and `$0.127040/M`; actual-rate economics remain
separate from the committed planning comparison.

The pending 791-request endpoint's `service_seconds_per_request` is decisive.
At or below 0.693940 seconds it eliminates the periodic overload; at or below
0.624546 seconds it also meets the earlier one-replica 90%-headroom rule.
Retail latency, availability, failures, reloads, storage, orchestration, and
all provider activity are deliberately unmodeled.

See `BACKGROUND_OVERFLOW_RESULT.json` for the input hashes, finite trajectory,
64-period trajectory, every raw cap, and tier-specific non-dominated points.
