# Startup qualification supervisor

`warmup-supervisor.py` is the shared startup supervisor for the SGLang runtimes
(`runtimes/glm-sglang`, `runtimes/kimi-k31` and the DeepSeek SGLang runtime).
Each bundle copies it as `warmup-base.py` and subclasses `Supervisor` for its own
health check and metrics.

`RUNTIME_PORT` is the loopback inference port. `WARMUP_PORT` exposes readiness
only after cold-shape and concurrency checks finish, and Desmond uses that
readiness endpoint. Startup qualification bounds its concurrency and
mixed-prompt bursts to the configured admission limits, while retaining all
cold single-prompt shapes. Test overload rejection and replica failover
separately; an intentional 503 is not a passing inference probe. Production
inference probes pin a deployment and require a complete 8-token response to
`Hi` within four seconds, so they cannot be rescued by routing their check to
another deployment.

The pinned GLM chat template recognizes `reasoning_effort: "low"` and `"high"`;
omitting the field or using another value selects its maximum reasoning budget.
In particular, `"none"` does not disable reasoning in this template. Use `"low"`
for bounded serving probes and inspect both content and reasoning deltas in streams.

Run supervisor tests with:

```sh
python3 -m unittest discover -s product/inference/runtimes/glm -p 'test_warmup*.py'
```
