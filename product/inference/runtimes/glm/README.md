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
