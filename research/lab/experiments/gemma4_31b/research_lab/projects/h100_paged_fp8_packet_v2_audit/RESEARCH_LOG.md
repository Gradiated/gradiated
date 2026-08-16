# Research log

## 2026-07-17 — terminal execution audit

- Question: is packet v2 an executable pinned-vLLM H100 paged-FP8 program rather than a descriptive specification?
- Action: traced its AST and reachable calls against the observed `6d4a8e6d2` official source signatures; verified packet and upstream artifact digests. No provider, owner, GPU, image, checkpoint, or compiler was touched, and no repair was made.
- Evidence: the first `set_current_vllm_config` call never enters its contextmanager, so `Attention` cannot register. Independently, metadata-builder constructor/build calls use incompatible signatures. K/V use Q-head geometry, caches are uninitialized except one slot, timing/counters are absent, `sweep` always fails, and the packet's selection digest is malformed. Full content-bound findings are in `AUDIT.json`.
- Interpretation: `fail_not_start_ready`. Do not authorize spend from these bytes; direct producer/consumer symbols exist but are unreachable and cannot yield the required matched sentinel or economic aggregation.

## 2026-07-17 — director admission

Activated after packet v2 claimed start-ready. This independent `$0` audit protects the next allocation from another program that names but does not invoke the native consumer.
