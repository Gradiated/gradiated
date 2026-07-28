# Adaptive-depth endpoint integration decision

Classification: `endpoint_ready_offline`.

The new director binding and all eight bound hashes matched. The six pinned
v0.5.15 runtime sources plus the project-local lifecycle adapter are frozen in
[ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_SOURCE_MANIFEST.json](ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_SOURCE_MANIFEST.json).
The manifest SHA-256 is `1eebff421da4299a51a2e82861571cc4da3c0f3a248653955d1b374f25a4f0e5`.

The lifecycle preserves one active depth across native producer output,
target-row packing, attention metadata, acceptance, KV destinations, and
scheduler stride. It selects depth 12 for batches 1–7 and depth 6 for batches
8 and above. Depth 12 admits the existing graph shape; depth 6 is explicitly
eager and cannot be padded or disguised as graph input.

The offline fixture result passed:

- threshold and 1→7→8→7 transitions, including batch 23;
- permutation with per-request row/position/mask preservation;
- cancellation, completion, and reused request-slot ownership;
- empty and partial NGRAM matches with bonus-only settlement;
- graph/eager selection, KV locations, scheduler offsets, and ragged result carriers;
- duplicate, empty-batch, unknown-completion, and live-slot reuse fail-closed cases.

Evidence is CPU/state integration evidence only. No provider, GPU, checkpoint,
endpoint request, latency, quality, or economic claim was made. The later
whole-request endpoint remains separately authorized and must consume this
immutable source/config manifest without changing the frozen rule.

Artifacts:

- [ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_RESULT.json](ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_RESULT.json)
- [ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_SOURCE_MANIFEST.json](ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_SOURCE_MANIFEST.json)
- [ADAPTIVE_DEPTH_CPU_FIXTURES.json](ADAPTIVE_DEPTH_CPU_FIXTURES.json)
