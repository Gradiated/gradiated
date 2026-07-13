# Experiment contract

Before execution, record:

- causal hypothesis and expected direction
- stock control and candidate change
- model/data/workload/software/hardware identities
- quality and correctness gates
- latency, throughput, availability, or SLO target
- maximum spend, wall-clock timeout, and teardown action
- exact command, seed, configuration, and output artifact paths

On failure, preserve the failure log and classify it as invalid, blocked, or falsifying. Do not silently retry a failed placement as if it were an accepted sample. Do not promote a component or synthetic result into a full product claim without a scope-matched end-to-end control.
