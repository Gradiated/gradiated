# SGLang generation energy estimates

The GLM, DeepSeek and Kimi SGLang bundles launch SGLang through `launch.py`.
The entrypoint adds optional ASGI middleware to the existing HTTP app; model
execution, scheduling and token accounting stay in SGLang. SMG's HTTP relay preserves the response bytes and the extra usage field.

A daemon thread reads NVML cumulative energy counters every 250 ms and sums the
GPUs explicitly assigned by UUID in `NVIDIA_VISIBLE_DEVICES`. Counter differences
give the average power over each measured interval, including power changes
between samples. The first reading, unsupported counters, counter resets and
gaps longer than two seconds fall back to the existing NVML power query.
Between samples the last interval's average power is integrated over monotonic
time and divided equally among overlapping
generation requests dispatched by the tokenizer manager after validation.
Starting or finishing a request updates the integral
before changing the divisor. No GPU reads or network calls run on the request
path. Energy during periods with no generation requests is excluded.

The interval average is extrapolated until the next sample, so short requests
and batch changes within an interval remain approximate. This improves the
power input, not allocation by tokens or scheduler batch membership.

This is a modeled allocation of measured GPU power. It includes time queued
inside SGLang, prefill, decode, speculative work and GPU baseline power while
requests are present. It does not distinguish their costs or include CPU,
networking or cooling. Request time in the SMG queue is outside the estimate.
The supported setup is one HTTP/tokenizer worker owning all assigned GPUs;
explicit multiple-tokenizer-worker launches omit estimates rather than charge
the same GPU power in each process. Separate replicas must have disjoint GPU
assignments. Container runtimes can rewrite `NVIDIA_VISIBLE_DEVICES` to `void`;
when testing a bundle inside a container, pass its explicit UUID assignment to
the server process after container startup. An unavailable assignment omits the
estimate.

Buffered completions and final streaming usage chunks carry
`usage.estimated_joules`. Streaming requires the existing `include_usage` option.
No field is added without valid readings for the whole request. Missing NVML,
unsupported power queries, ambiguous GPU assignments, gaps longer than two
seconds, and sampler errors leave inference operational. First requests before
the initial power sample also omit the field. Compressed or oversized responses
pass through, and disconnected requests release their attribution share.

The gateway validates the optional number and stores it as
`properties.estimated_joules` through normal generation settlement.
The generation log API returns the stored estimate, or null for older records.
Cancellation before final usage has no complete estimate. A successful retried
generation describes the reported attempt; unreported work on earlier attempts
is not inferred. Energy does not change billing.

Ship the updated worker/ingestion contract before the gateway emits the new
property. Runtime bundles can ship independently: older gateways ignore the
extra usage field. These changes do not update production bundle digests or
deploy any model.

Run the CPU checks from the repository root:

```sh
python3 -m unittest discover -s product/inference/runtimes/energy -p 'test_*.py'
```

Each bundle also runs these checks during its build verification. Runtime
configuration tests cover the GLM, DeepSeek and Kimi launch commands. GPU power
accuracy and overhead still need validation on a serving replica before rollout.
