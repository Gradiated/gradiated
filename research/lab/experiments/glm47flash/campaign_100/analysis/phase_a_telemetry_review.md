# Phase A independent telemetry and economics review

Review role: telemetry/economics subagent, offline and independent of the RunPod
mutator. No RunPod API or resource was accessed or changed during this review.

## Result

The version 1.0.0 evidence contracts are suitable for Gate A after coordinator
review. They fail closed on omitted or unknown fields, non-pinned images, missing
raw files, hash/size mismatch, non-monotonic percentiles, internally impossible
request counts, underreported conservative cost, altered SLO thresholds, and
teardown that lacks API verification.

The frozen contract manifest is `specs/CONTRACT_MANIFEST.json`. It content-addresses
the schemas, arithmetic/admission validator, and explanatory contract. The
dependency-free validator is `specs/validate_contracts.py`.

## Independent conservative arithmetic

Let `h` be the recorded GPU hourly price, `s` authoritative allocation seconds,
and `p` provider-reported allocation cost. GPU cost is:

`C = max(p, h * s / 3600)`

No allocation discount, free startup interval, or provider rounding-down is
assumed. Each token metric assigns the full allocation cost to its own denominator:

- input: `C * 1,000,000 / input_tokens`
- output: `C * 1,000,000 / output_tokens`
- blended: `C * 1,000,000 / (input_tokens + output_tokens)`
- output-equivalent: `C * 1,000,000 / (output_tokens + w * input_tokens)`, where
  `w` is the predeclared input-token weight
- SLO-compliant blended: `C * 1,000,000 / (slo_input_tokens + slo_output_tokens)`

The full cost remains in the numerator for the SLO metric; failed and late work
therefore increases SLO-compliant cost rather than disappearing. The artifact
schema separately requires total and SLO-compliant token counts.

Worked check: at `$2.99/hour`, 600 seconds costs `$0.4983333333333333333333333333`
even if the provider reports `$0.49`. For 800,000 input and 200,000 output tokens,
the GPU-only costs per million are `$0.6229166666666666666666666666` input,
`$2.491666666666666666666666666` output, and
`$0.4983333333333333333333333333` blended. With input weight 0.25, output-equivalent
cost is `$1.245833333333333333333333333` per million. If only 900,000 blended
tokens are SLO-compliant, SLO cost is `$0.5537037037037037037037037037`.

GPU-only economics do not imply fully loaded COGS. The contract reports an
explicit non-GPU sensitivity fraction and reserved dollars but does not silently
set host, network, engineering, or fleet-idle cost to zero.

## Admission and watchdog review

Every create request must independently pass both contracts immediately before
mutation:

1. The admission record binds a signed baseline, inventory snapshot, watchdog,
   exact `$100.00` cap, frozen phase/cumulative-cap mapping, conservative current
   additional spend, hourly price, and maximum deadline.
2. Exact exposure is `hourly_price * maximum_deadline_seconds / 3600`. A recorded
   exposure below that value rejects; the recorded exposure is used for both
   projected phase and campaign spend.
3. Admission rejects an unsigned baseline, uncertain reconciliation, Phase A GPU
   use, any active campaign pod, a changed phase cap, or projected spend above
   either applicable cap.
4. The watchdog must be an independent process with an absolute deadline, cleanup
   on deadline and orchestrator exit, cleanup even if harvest fails, an API deletion
   verification step, a poll interval no longer than 60 seconds, and a durable log.

Passing these contracts is necessary but not sufficient authorization: the
coordinator remains the only RunPod mutator and must query the account before and
after each mutation.

## Test evidence

TDD was used: the initial tests failed because no validator existed. The minimum
implementation was then added and tightened with cross-field checks. Current
results:

- `python3 -m unittest discover -s campaign_100/tests -p 'test_artifact_*.py'`:
  8 passed.
- `python3 -m unittest discover -s campaign_100/tests -p 'test_economics_*.py'`:
  11 passed.
- All seven JSON contracts/manifests parse with `python3 -m json.tool`.
- `validate_contracts.py` compiles with `python3 -m py_compile`.

## Risks and required coordinator controls

- The validator cannot establish authoritative account lifetime spend. The
  coordinator must derive current additional spend from the reconciled provider
  inventory/allocations and use the larger defensible value when records differ.
- Aggregate SLO token fields are auditable only if the replay harness retains
  request-level outcome/latency/truncation records as a hashed `request_outcomes`
  raw file. The validator denies artifacts that only contain aggregate counters.
- `memory_throughput.status = unsupported` is permitted only with explicit null
  metric fields. It avoids fabricated HBM evidence but may leave causal attribution
  too weak for a promoted performance claim.
- The artifact contract requires a short profiler trace. A result lacking it is
  intentionally inadmissible as decisive evidence; compatibility-only smoke output
  should not be mislabeled as a promoted A/B result.
- Provider price and provider-reported cost are evidence inputs, not trusted
  conclusions. Preserve their raw response identity alongside the artifact when
  available.
- A validator `pass` is not a quality or performance pass. It means only that the
  evidence package is structurally complete and internally conservative.
