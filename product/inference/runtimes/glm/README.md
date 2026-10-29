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

The entrypoint serves `dealignai/GLM-5.3-Flash-UNCENSORED-NVFP4` at revision
`745aac2ff0f10acf961f396df3f9418598aa7327` with tensor parallelism 1,
four active decode sequences, two MTP draft tokens, FP8 KV cache, the GLM tool/reasoning parsers, and the existing startup
qualification supervisor. `RUNTIME_PORT` is the loopback inference port;
`WARMUP_PORT` exposes readiness only after cold-shape and concurrency checks
finish. Desmond should use that readiness endpoint. `HF_HOME` selects the
model cache. The production Kubernetes Rollout uses the node-local disk at
`/home/runtime/.cache/huggingface`, shared across allocations on that host.
Hugging Face downloads the pinned revision when files are absent and reuses
completed blobs on subsequent starts. No network volume or RAM-backed checkpoint
cache is required. The cache is disposable: a host reset can remove it, and the
next rollout downloads it again before admission opens. Leave enough disk space
for the checkpoint and retained revisions; use the Hugging Face cache tools to
remove unused revisions while preserving weights used by running processes.
The job reserves 224 GiB of host RAM. First startup can also include
GPU-kernel compilation and autotuning.
The runtime launcher sets `GRADIATED_RUNTIME_ROOT`.

The immutable stock release remains available for rollback. Dealign has a separate
catalog identity, `dealignai/glm-5.3-flash-uncensored-nvfp4`; its modified base
weights do not qualify existing stock-model LoRA adapters. A release selecting
Dealign must omit `adapters`, `lora_enabled`, and the LoRA environment settings.
Publishing this bundle does not change the selected production runtime: pin a
qualified release in `gpu/runtimes.json` and the GPU `models.json` to roll it out.

On a B300, 60-second synthetic runs with 1,024 generated tokens measured median
per-request decode rates of 161, 188 and 186 TPS with one, two and three draft
tokens, respectively, at concurrency one. Two drafts measured 147 TPS at
concurrency two and 107 TPS at concurrency four. The longer-prompt concurrency-one
run measured 179 TPS median and 169 TPS minimum across ten requests. Two drafts and one simultaneous decode meet the measured 150 TPS target.
The selected production setting is four simultaneous decodes per GPU, favoring
capacity at approximately 107 TPS per request. Remeasure for other prompt
lengths and workloads. Under the selected 16 CPU / 224 GiB limits, a three-minute
concurrency-four run completed 75 requests without errors at 107 TPS median per
request and 416 aggregate TPS. An 8,036–8,041-token prompt run completed 20
requests without errors at 88 TPS median per request.

`--max-num-seqs 4` limits simultaneous decoding; additional HTTP requests can
queue. Add TP1 replicas to increase simultaneous serving capacity.
The production target is eight TP1 replicas at concurrency four, with 16 CPU and
224 GiB host RAM per replica. Cold-weight loading and startup qualification
peaked at 188 GiB under those cgroup limits. Eight replicas fit as four on the
4-GPU B300 host and four beside DeepSeek on the 8-GPU B300 host, after stock GLM
drains. Placement permits several replicas per host.

The startup supervisor checks bursts through concurrency sixteen, including
queue completion within its timeout.

Retire stock GLM only after the new deployment passes production verification.
`autoscaling.paused_replicas: 0` renders KEDA's paused-replica annotation, which
sets the old Rollout to zero while retaining its immutable rollback profile.
Retiring the base also requires marking its trained adapters unavailable;
retain their artifacts and training history.

Reproduce the initial concurrency screen against an isolated test runtime:

```sh
mkdir -p .agents/runtime/glm-dealign
python3 infra/environments/prod/runpod/deepseek-v4-1-flash/benchmark.py \
  --url http://127.0.0.1:28085 \
  --model dealignai/GLM-5.3-Flash-UNCENSORED-NVFP4 \
  --label glm-dealign-tp1-mtp2 --concurrency 1,2,4 --tokens 512 \
  --output .agents/runtime/glm-dealign/concurrency.json
```

The pinned chat template recognizes `reasoning_effort: "low"` and `"high"`;
omitting the field or using another value selects its maximum reasoning budget.
In particular, `"none"` does not disable reasoning in this template. Use `"low"`
for bounded serving probes and inspect both content and reasoning deltas in streams.

Build the Dockerfile with `product/inference` as context and the pinned GPU
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

The immutable stock release (runtime `glm-e74e88f23ba1`) restricts LoRA wrappers
to the trained attention projections. The Dealign entrypoint rejects
`LORA_ENABLED=true`; the following adapter qualification applies to the stock
release only. GLM KDA packs q/k/v together with three untrained gate branches;
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
