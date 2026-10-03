# GLM-5.3 Flash runtime

`bundles/glm-5-3-flash` builds a relocatable CPython 3.12.13 runtime for
`ubuntu24-cuda13-amd64-v2`. The vLLM package and distribution metadata come from
the immutable upstream image pinned in the Dockerfile, version
`0.28.1rc1.dev580+g385dce36b`, matching the existing production runtime. The narrow side-cache slot-mapping
fix in `slot-mapping.patch` is applied with zero fuzz. It pads disabled,
out-of-range and batch-padding slots instead of reading beyond their block-table
rows; full attention slots remain unchanged. The GPU regression reproduces the
long-prompt failure on the pinned upstream runtime (upstream issue #53982).
The remaining dependencies are version-pinned and hash-locked; the lock uses a seven-day release cutoff.

The entrypoint serves the pinned GLM model revision with tensor parallelism 2,
FP8 KV cache, the GLM tool/reasoning parsers, and the existing startup
qualification supervisor. `RUNTIME_PORT` is the loopback inference port;
`WARMUP_PORT` exposes readiness only after cold-shape and concurrency checks
finish. Desmond should use that readiness endpoint. `HF_HOME` selects the
model cache. The production Nomad job uses `/dev/shm/gradiated/model-cache`
because memory-mapped weight loading from RunPod’s network-backed cache is slow.
Allow at least 330 GB of shared memory for the pinned checkpoint, in addition to
serving memory. Cache contents survive process restarts and are lost with the
host; a cold host downloads the pinned checkpoint again. The job reserves
400000 MiB of host RAM. Keep the network-volume checkpoint when prewarming an
existing host, and verify copied weight checksums before starting the canary.
Check `/dev/shm` free space separately from host RAM: unused checkpoint files can
fill tmpfs while `MemAvailable` remains large. Leave headroom for worker IPC and
move only verified, unused checkpoint files to disk while preserving their cache
paths. First startup can also include GPU-kernel compilation and autotuning.
The runtime launcher sets `GRADIATED_RUNTIME_ROOT`.

Build the Dockerfile with `product/inference` as context and the pinned Nomad
base as the `runtime-base` build context. The `verify` target checks dependency
compatibility, imports vLLM in that base, and verifies the GLM architecture is
registered. The `artifact` target exports `runtime.tar.gz`. CPU verification does
not qualify GPU execution; production rollout must also pass startup warmup
and real gateway requests.

Run supervisor tests with:

```sh
python3 -m unittest discover -s product/inference/runtimes/glm -p 'test_warmup*.py'
```

On an explicitly allocated test GPU, run the side-cache regression with:

```sh
GRADIATED_GLM_GPU_TEST=1 /bundle/python/bin/python3 product/inference/runtimes/glm/test_slot_mapping.py
```

The test covers prompt positions through 1,047,000 and checks full attention,
a one-block side cache, disabled mapping, and padded batch tokens.

When LoRA is enabled, the entrypoint restricts wrappers to the trained attention
projections. GLM KDA packs q/k/v together with three untrained gate branches;
MLA packs q_a and kv_a together. The pinned runtime needs these packing maps to
apply every PEFT projection, rather than silently ignoring fused modules. Gate
branches stay unwrapped because their sliced inputs are not contiguous and the
training adapters do not target them. CPU bundle verification checks the exact
mapping; real GPU qualification covers both TP2 and TP4 inference.

The MLA projection has a separate pinned backport from
[vLLM PR #49007](https://github.com/vllm-project/vllm/pull/49007), source
`ad90d0c6187e5f355db7bdb7d8f3ae5f91bf1d8c`. The upstream draft is closed and
unmerged; this bundle therefore qualifies it independently. The backport adapts
three changed call sites, current chunk/request indexing and sparse masked MHA,
accepts the materialized three-dimensional KV output, and avoids CPU residency
shortcuts that freeze absent adapters during CUDA graph capture. GPU token
mappings mask base rows dynamically. It preserves sparse
attention and applies the KV delta during prefill, cached-context reconstruction
and absorbed decode; accepting an adapter without these paths drops trained
weights silently. The loader and native adapter caches are unchanged.

The numerical regression uses rank 2 and 8, TP2/TP4 head geometry, mixed base
and adapter routing, strided inputs and a float32 oracle. Bundle verification
runs the CPU path. On an allocation with reserved GPUs, run:

```sh
GRADIATED_REQUIRE_GLM_LORA=1 GRADIATED_GLM_LORA_GPU_TEST=1 \
  python3 -m unittest discover -s runtimes/glm -p 'test_mla_lora.py'
```

Qualification checks the trained adapter against independent FP32 math on the
actual runtime inputs, requiring every MLA layer during both prefill and decode,
one BF16 output rounding step, no changes to inactive rows and no nonfinite
active corrections. All 11 MLA layers passed on every TP2 and TP4 rank: worst
relative FP32 error was below 9e-7 across approximately 5,000 corrections per
rank. Real TP2/TP4 cache eviction, long prompts through 131K tokens, prefix-cache
reuse, streaming and cancellation also passed. These checks qualify the pinned
runtime and trained rank-two adapter; other runtime versions need qualification.

Absolute whole-model logprob tolerances are unsuitable for this pinned FP8
runtime: the LoRA-disabled, same-process, fresh-cache control itself showed mean
differences of 0.47-0.55 and maxima of 1.52-2.25 on repeated long requests.
This control does not establish adapter task quality or bitwise determinism;
those require separate evaluation.
