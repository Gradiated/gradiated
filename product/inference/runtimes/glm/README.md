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
catalog identity, `dealignai/glm-5.3-flash-uncensored`; its modified base
weights do not qualify existing stock-model LoRA adapters. A release selecting
Dealign must omit `adapters`, `lora_enabled`, and the LoRA environment settings.
Publishing this bundle does not change the selected production runtime: pin a
qualified release in `gpu/runtimes.json` and the GPU `models.json` to roll it out.
The worker waits for the catalog model to become available before SDK
qualification, so a slower catalog rollout does not reject the runtime process.

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
Require node affinity to instance IDs `01a0f19d-1ff3-7613-8cbf-81b693c0f0d4`
and `01a0fbf7-5276-700b-903b-7e04da150ed6`. Host
`01a0fbf8-06fc-7658-96e1-ae72f7dba135` is user-owned capacity and must not be
used for this deployment or further experiments, even if it is uncordoned.

The startup supervisor checks bursts through concurrency sixteen, including
queue completion within its timeout.
It explicitly warms active occupancies one through four, including three,
and a pair of prefills alongside a short request when admission limits permit.
These shapes must run before readiness so MTP batch specializations are compiled
before serving traffic. Queue limits bound the qualification bursts.

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

For isolated mixed-context tests, `GLM_PREFILL_TOKEN_BUDGET=2048` adds
`--enable-chunked-prefill --max-num-batched-tokens 2048` to the bundle entrypoint.
The variable must be an integer of at least four, matching the sequence limit. When unset, vLLM retains its scheduler
defaults; the pinned runtime on a single B300 selects chunked prefill with a
16,384-token budget. This setting changes the prefill token budget, not the
four-sequence limit. Keep test runtimes outside production routing and compare
against the same model revision, GPU, MTP settings, and concurrency.

`GLM_LONG_PREFILL_TOKEN_THRESHOLD=2048` instead caps each request's prefill
contribution per scheduler iteration. Leave `GLM_PREFILL_TOKEN_BUDGET` unset to
keep the pinned B300 default total budget of 16,384, or set it explicitly to
16,384. The per-request cap leaves batch budget for new short prefills when
sequence capacity is available. The pinned scheduler applies this cap even to
a lone long request, so measure its long-context TTFT and throughput cost.
The value must be positive and no larger than the 1,048,576-token model window;
unset keeps the per-request cap disabled. Admission still depends on the
four-sequence capacity and queue policy.

`GLM_PREFIX_MATCH_UNIT=128` enables prefix caching and forwards
`--prefix-match-unit 128` together with the native
`--enable-mamba-fine-grained-prefix-cache` checkpoint option. This controls prefix matching independently of the
physical cache page size: `--block-size 128` alone does not establish 128-token
reuse for the hybrid attention/state cache. Qualify the actual cached-token
counts, repeated and extended prefixes, divergent prefixes, and long-context
retrieval with MTP enabled before selecting a release. The native checkpoint
option retains its applicability and correctness guards; matching at 128-token
boundaries does not guarantee a reusable state at every boundary. Include
several warm repeats and changed-prefix controls in qualification.
`prefix-tail.patch` retains a reachable full-attention tail when the prompt
length is exactly divisible by the matching unit. Prefix lookup leaves the last
prompt token for logits; caching only the boundary at the full prompt length
makes that entry unreachable and forces coarser reuse. With 128-token matching
and MTP, a 32,768-token prompt should reuse 32,512 tokens. CPU bundle verification
checks physical and logical boundaries, partial prefill, changed prefixes and
eviction against the pinned vLLM cache manager. It does not qualify hybrid GPU
state restoration; require repeated, extended and divergent prompts on an
isolated GPU before promoting this bundle.

The entrypoint and host profile require a positive divisor of the fixed
128-token launch block. Qualification of 128 does not establish performance
or cache correctness for other units.
Unset preserves the
pinned runtime's matching policy.

The mixed-context benchmark sends one long synthetic chat prompt followed by
six short prompts at 250 ms intervals, with 256 generated tokens per request.
A second ordering waits for three short streams to emit their first tokens before injecting the long prompt,
so the test also measures prefill interference with active decodes.
It prepares the fixtures before timing, measures their chat-template token counts
through `/tokenize`, checks exact returned usage and complete streams, and records TTFT, client SSE
event gaps, per-request decode rate, and aggregate output throughput. MTP can
emit several tokens in one SSE event, so event gaps are not per-token latency.
The workload uses seeded synthetic service logs and tests scheduling and streaming,
not semantic quality. Each request has a distinct seeded prefix to avoid shared-prefix
cache hits. `--protocol completions` selects random-token prompts for diagnostics.
`--quality-smoke` also checks retrieval of known markers placed at the start,
middle, and end of 512/32K/128K contexts; it records correctness separately from
latency measurements. The host agent accepts the budget in the pinned runtime profile environment; changing
a Kubernetes container environment directly remains unsupported.

```sh
python3 product/inference/benchmarks/mixed_prefill.py \
  --url http://127.0.0.1:28100 --label baseline \
  --long-tokens 32768,131072 --repeats 3 --quality-smoke \
  --output .agents/runtime/glm-mixed-baseline.json
```

For million-token interference, test `--long-tokens 1000000,1047552` with
`--output-tokens 1024`. The second prompt size plus output budget exactly fills
`--max-model-len 1048576`. Run the benchmark using the bundle's Python and pass
`--tokenizer-path` pointing to the verified model snapshot to prepare long chat
fixtures efficiently. The benchmark validates the local token count against the
runtime's `/tokenize` response. `--fixture-cache` reuses those exact prepared
fixtures across server restarts. Keep that cache under `.agents/runtime/` or the
test host's temporary directory. `--quality-contexts 512,1000000,1000000` extends
the marker smoke checks to million-token contexts. Smaller-context results do
not qualify million-token serving.

The benchmark allows prefill within the 630-second request deadline and starts
the 30-second stream idle limit after first output, matching the gateway policy.
It cannot distinguish an accepted queued request from active prefill.
For a diagnostic run that observes backend completion
beyond those limits, set `--response-idle-timeout 690 --request-deadline 900`
and report it separately. Use a different `--seed-offset` for each timeout mode
to keep prefix-cache hits from making the production-limit probe artificially fast.

`MAX_QUEUED_TOKENS` and `MAX_QUEUED_REQUESTS` are optional positive integer
admission limits in the runtime profile environment. Unset preserves unlimited
frontend admission. The token threshold counts full prompt lengths of requests
still in prefill, including running prefills; it excludes requests already
decoding. Partial prefill progress and prefix-cache hits do not reduce that count
until prefill finishes. The pinned runtime checks the existing backlog, so the
next admitted request can overshoot the threshold. This is backpressure, not a
maximum input length. Rejections are HTTP 503 before generation, eligible for the
gateway's zero-usage capacity retry on another replica. Requests already accepted
or streaming cannot safely be replayed to hide a slow queue.

The native request limit counts running plus waiting requests. With four
active sequences, `MAX_QUEUED_REQUESTS=6` permits two additional requests when
all four slots are occupied. It is not a strict waiting-only limit: more than
two can wait if fewer than four requests are running. It imposes no queue-age
bound. Leave `MAX_QUEUED_TOKENS` unset for the request-count-only policy.
The gateway retries a zero-usage capacity rejection on one other replica and
returns HTTP 429 if both reject; accepted requests do not gain that failover.
A pinned four-second inference probe must still complete on its own replica.

The `/metrics` endpoint also exports `gradiated_runtime_prefill_backlog_prompt_tokens`,
`gradiated_runtime_inflight_requests`, the configured queue limits (`-1` means
unlimited), and `gradiated_runtime_queue_telemetry_available`. These use the exact
frontend counters read by admission, alongside vLLM's native running/waiting and
latency metrics. No request content or per-request labels are exposed.

Startup qualification bounds its concurrency and mixed-prompt bursts to the
configured admission limits, while retaining all cold single-prompt shapes.
The default policy still checks concurrency sixteen. Test overload rejection
and replica failover separately; an intentional 503 is not a passing inference
probe. Production inference probes pin a deployment and require a complete
8-token response to `Hi` within four seconds, so they cannot be rescued by routing
their check to another deployment.
