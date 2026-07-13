# Campaign 100 telemetry and economics contracts

Version `1.0.0` is frozen for Phase A. JSON objects reject unknown fields. The
dependency-free executable validator is `validate_contracts.py`; nonzero exit is
a hard artifact or admission failure.

`gpu_artifact.schema.json` binds the experiment and workload identities, exact
checkpoint/runtime/image identities, hardware/provider allocation, frozen SLO,
request metrics, raw telemetry identities, profiler evidence, conservative cost,
and DELETE-204/GET-404 teardown. `gpu_metrics.schema.json` and
`gpu_telemetry.schema.json` are the referenced metric contracts.
`request_outcome.schema.json` defines each row of the hashed request JSONL. The
validator derives aggregate request/token/SLO counters from those rows and
recomputes every throughput field from tokens, completions, and wall time.

`economics.schema.json` records GPU-only economics. Arithmetic uses decimal
values and assigns the full conservative allocation cost to each denominator:

- conservative GPU cost is the maximum of provider-reported cost and
  `hourly_price * allocation_seconds / 3600`;
- input, output, and blended token metrics divide by their respective measured
  token counts;
- output-equivalent tokens equal `output + input * input_token_weight`;
- SLO cost divides only by tokens from completed SLO-compliant requests;
- non-GPU cost is not claimed as zero; a declared sensitivity fraction is
  reported separately from GPU-only economics.

`budget_admission.schema.json` is evaluated immediately before every create
request. Admission requires the signed campaign baseline, authoritative or
larger-defensible reconciliation, zero active campaign pods, content identities
for the inventory and watchdog, and maximum-deadline exposure within both the
phase cumulative cap and exact `$100.00` campaign cap.

`watchdog.schema.json` requires an independent process with an absolute deadline,
cleanup on deadline and orchestrator exit, cleanup despite harvest failure, API
deletion verification, and a durable log. A create operation must not begin until
both watchdog validation and budget admission pass. Budget admission dereferences
and hashes the baseline, current inventory snapshot, and watchdog contract; hash
strings or signed-off booleans alone are not admission evidence.
