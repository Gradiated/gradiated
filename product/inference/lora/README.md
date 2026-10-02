# vLLM adapter loading

This is an opt-in, allocation-local wrapper around the existing vLLM engine.
The GLM bundle includes it; `lora_enabled` defaults to `false`. This PR adds the
runtime side. The private metadata/grant API and gateway selection follow in the
remaining stack, so leave the feature disabled until those and GPU qualification
are complete.

`manager.py` owns cold preparation, CPU admission and disk LRU. `artifacts.py`
verifies and materializes archives. `server.py` protects CPU entries for the
lifetime of each proxied request and enforces one allocation-wide concurrency
limit. vLLM owns GPU slots, batching and GPU LRU; there is no second GPU cache or
adapter placement service.

## Request and startup paths

A request identifies an immutable adapter as `ft-<version UUID>-<full SHA256>`.
The gateway provides the authenticated workspace in `X-Gradiated-Workspace`.
On a CPU hit the request goes straight to vLLM. Otherwise one preparation at a
time per allocation performs these steps; concurrent requests recheck the cache
after acquiring the preparation lock:

1. Obtain authorized version metadata and a short-lived download grant if needed.
2. Reuse verified disk files, or stream the S3 archive into a staging directory.
3. Verify archive size/checksum, safe file names and safetensors structure.
4. Check base model/revision, rank, decoder layer coverage and expert completeness.
5. Evict idle CPU entries until slot/byte limits permit the adapter, then load it
   through vLLM's loopback-only adapter API.

The metadata source is the existing task version, not a separate hosting record.
The private grant request is `{workspace_id, version_id, sha256}`; its response
composes `{workspace_id, version: TaskVersion, download: AdapterDownload}`. URLs
are temporary and never stored in task versions. A cold load refreshes its grant;
a valid disk hit after restart still needs version/ownership metadata, but does
not download the archive again. The production list is `{data: [{workspace_id,
version_id, sha256}]}`, filtered by the requested base model. PR 3 will author
these private routes using the existing contract schemas and signing service.

After the existing base-engine warmup qualifies, each allocation independently
preloads compatible current production versions until CPU capacity or the
startup deadline is reached. Preload does not evict earlier CPU entries to cycle
through the list. Unloaded versions remain eligible for on-demand preparation.
`LORA_PRELOAD_SECONDS` defaults to 600; the deadline is checked between bounded
loads, so one in-progress load can finish after it. Readiness opens after this
best-effort preload. A production-list outage still permits base serving and
on-demand loads; an uncertain vLLM load/unload failure closes readiness and exits
the wrapper so Nomad's existing task restart policy can recover it.

## Cache ownership

| Tier | Owner | Eviction behavior |
| --- | --- | --- |
| S3 archive | Existing training artifact storage | Durable source of truth |
| Allocation disk | Wrapper, byte-bounded LRU | Removes files; CPU-resident tensors can remain usable |
| CPU tensors | vLLM, admitted by wrapper slot/byte limits | Unregisters an idle adapter; retains disk files when present |
| GPU slots | vLLM | Reuses CPU tensors without an S3/disk fetch |

Active requests protect their entries from wrapper eviction. Streaming flushes
upstream chunks as they arrive; disconnect/error cleanup closes the upstream
connection before releasing the reference. A restart recovers and revalidates
own disk directories, removes incomplete staging directories, and starts with
empty CPU residency. `cpu_resident` in the private status response describes
registered CPU entries, not GPU residency. GPU residency is not durable state.

Disk reservations include the compressed archive, declared extracted bytes and
manifest space, and are made before each file is written. CPU admission charges
raw tensor bytes times `2 * TP`, conservatively allowing for worker replication
and loading/conversion overlap. This is an accounting limit for adapter tensors,
not a measurement or limit of whole-process RSS. Provision headroom for the base
engine, Hugging Face tmpfs, KV cache, request buffers and all colocated allocations;
actual TP2/TP4 peak memory must be qualified before enabling production.

## Configuration and isolation

TP, model revision, served name and concurrency come from the existing vLLM
command. Layer/expert geometry comes from the pinned model's `config.json`,
including nested `text_config`; the adapter does not choose host settings.
`tensor_parallel_size` in the Nomad job controls both GPU allocation and the base
engine command. The wrapper verifies the assigned GPU UUID count matches it.
The same artifact identity can serve on separately qualified TP2 and TP4 engines.

| Setting | Source/default |
| --- | --- |
| `LORA_ENABLED` | Nomad `lora_enabled`, false |
| `MODEL_ID` | Existing deployment's public base model ID |
| `LORA_GPU_SLOTS` | Nomad `lora_gpu_slots`, 8 |
| `LORA_CPU_SLOTS` | Nomad `lora_cpu_slots`, 64; must cover GPU slots |
| `LORA_MAX_RANK` | Nomad `lora_max_rank`, 8; actual adapter rank may be 2 |
| `LORA_CPU_CACHE_BYTES` | Explicit allocation budget; zero defaults fail startup when enabled |
| `LORA_DISK_CACHE_BYTES` | Explicit allocation budget; zero defaults fail startup when enabled |
| `LORA_DOWNLOAD_HOSTS` | Comma-separated exact S3 HTTPS host allowlist |
| `LORA_GRANTS_URL` / `LORA_PRODUCTION_URL` | Private HTTPS metadata API endpoints |
| `LORA_CONTROL_TOKEN_FILE` | Host-provisioned `/etc/gradiated/adapter-control.token` |
| `LORA_CACHE_DIR` | Entrypoint sets `${NOMAD_ALLOC_DIR}/lora`, separate for each allocation |

The wrapper and engine bind to different loopback ports. Existing authenticated
host ingress reaches the wrapper; the raw vLLM load/unload APIs are not exposed.
`POST /internal/adapters/prepare` accepts only a name and workspace, not file
paths or URLs. Probe/status require the additional private control header.
`/health`, `/metrics`, `/v1/models` and completion routes remain available.
The existing deployment release advertises `lora_enabled: true` when opted in,
allowing later selection to distinguish capable allocations during rollout.
Existing releases without this field keep their original heartbeat digest.

The loader accepts PEFT decoder LoRA archives containing `adapter_config.json`,
`adapter_model.safetensors` and optionally `README.md`, flat or under `adapter/`.
BF16, F16 and F32 weights are accepted; per-expert 2D and fused 3D MoE layouts are
checked, and the vLLM format flag is derived from the tensors. Unsupported PEFT
features, links, traversal, executable files, incomplete tensors and checksum
mismatches fail before loading. vLLM performs model-specific module compatibility
checks. This does not qualify vision-tower adapters or prove numeric correctness
on GLM; real-artifact/reference, cold/hot latency, cancellation/KV isolation and
colocated TP2/TP4 tests remain production gates.

## Verification

```sh
python3 -m unittest discover -s product/inference/lora -p 'test_*.py'
uv tool run ruff check product/inference/lora
uv tool run ruff format --check product/inference/lora
```

Tests use synthetic weights and local HTTP engines. CI also runs them in the
pinned GLM bundle's Python environment; no GPU qualification is implied.
