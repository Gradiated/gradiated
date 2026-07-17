# SM120 current-AWQ venue and economic gate

## Question

Is there one currently orderable, content-bound RTX PRO 6000 Blackwell Server Edition (`sm_120`, 96 GB) venue whose rate, execution contract, and physical envelope justify a later exact current-AWQ c32 load measurement against the campaign's `$0.514/M` target?

## Why this matters

The exact full-model L40S paths are now measured sub-gate or technically closed. The terminal `current_awq_sm120_admission_screen` established that unchanged vLLM `v0.25.1` contains the exact GLM-Lite architecture, SM120 build targets, compressed-tensors WNA16 dense and MoE selection, and ample analytical c32 capacity, but it stopped at the device-only MLA/graph/no-fallback boundary before checking a venue or rate. A 96-GB SM120 measurement is a materially different hardware intervention and does not depend on exit-35 cleanup.

## Fixed evidence

- Exact checkpoint revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, manifest SHA-256 `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`, compressed-tensors group-32 W4A16.
- Workload: cache off, 8,192 input / 1,024 output, c32 primary, complete requests within 300 seconds; latency below that envelope is secondary.
- Economic target: `$0.514/M` output tokens. At all-in rate `R`, required sustained throughput is `R * 1,000,000 / (3,600 * 0.514)`.
- Consume `../current_awq_sm120_admission_screen/artifacts/SM120_AWQ_ADMISSION_SCREEN_2026-07-16.json`; do not repeat its source/config/backend-presence work.
- Use the shared accelerator inventory for stable RTX PRO 6000 Blackwell Server geometry. Shared GPU prices are fresh but omit this accelerator, so one targeted missing-accelerator rate check is allowed.

## Scope and stop rule

Within 900 seconds and `$0`, inspect current public evidence for at most three exact or execution-equivalent 96-GB SM120 venues. Bind accelerator identity, availability/orderability, region, host shape, container/driver privileges needed by the unchanged published vLLM artifact, capacity type, billing minimum, storage/network inclusions, and retrieval time. Prefer primary venue documentation and retain reproducible citations or captures. Do not use credentials, contact sales, request capacity, create an account, build a controller, download weights, run CUDA, or mutate any provider.

For the strongest venue only, calculate the authoritative throughput gate and a conservative resource envelope from the measured L40S endpoint plus SM count, bandwidth, memory, and expected c32 effects. This is an admission bound, not transferred throughput. Return exactly one terminal result:

- `NOMINATE_TARGET_GPU`: one currently orderable venue/rate and unchanged-container contract exist, and a conservative physical envelope does not rule out the required throughput;
- `ECONOMIC_CLOSE`: the best bound rate demands throughput outside a conservative physical envelope;
- `VENUE_CLOSE`: no current orderable exact topology or sufficiently bound rate/execution contract exists.

No successor preflight is authorized. A nomination changes the portfolio by admitting one later target-GPU exact-load c16/c32 falsifier after separate provider authority; a close parks SM120 until genuinely new availability or rate evidence appears.

## Artifact contract

Produce one compact JSON with source identities, venue/rate fields, required-throughput calculation, physical-envelope assumptions, uncertainty labels, and terminal decision. Append a concise `RESEARCH_LOG.md`; do not edit shared tools or another project.
