# vLLM adapter loading

The GLM bundle includes an opt-in adapter loader. It is a control service, not an
inference proxy. Completion requests, streaming, cancellation, batching and CPU/GPU
adapter caching remain with vLLM. The private metadata API and gateway integration
are implemented. `lora_enabled` defaults to false in the job template. The production GLM vars
enable it with the independently qualified BF16-training/FP8-serving revision pair.

## Request path

The gateway authorizes an exact task version in its workspace and sends a normal
inference request with the internal model name
`<workspace UUID>/<resolved version slug>`. Public requests still use the
existing version or task production slug. The gateway does not prepare adapters.

On first use, vLLM's native `LoRAResolver` plugin calls the allocation's loopback
`POST /internal/adapters/resolve` with `{name, workspace_id}`. The loader:

1. Obtains existing task-version metadata and a short-lived download grant.
2. Reuses verified local files or downloads the S3 archive into a staging directory.
3. Verifies size/checksum, safe archive contents, base revision, rank, layer coverage
   and expert completeness.
4. Returns the retained local path and tensor format flag, without calling vLLM.

The resolver returns a native `LoRARequest`; vLLM assigns its ID, coalesces requests
for the same name, registers it and handles inference. Registered requests use
vLLM's native CPU/GPU cache. The plugin uses a worker thread for the blocking local
file request, so downloading does not block the vLLM API event loop. Errors fail
closed with a bounded message; they never fall back to the base model.

The loader never forwards completions, reads token streams, holds inference slots,
tracks active requests, unloads adapters or restarts the engine. Startup preload
and qualification retain the native load API. Materialization locks are released
before calls into vLLM, allowing concurrent native resolution without deadlock.
Archives of at least 8 MiB use at most eight equal, non-overlapping ranges, all
started together and written into one staging file; smaller archives use a single
GET. Each range has at most twelve attempts, capped at five seconds and the
original cold deadline. Timeouts and DNS lookup failures resume from bytes already
written; DNS retries pause for up to one second within that deadline. Queued
chunks cannot delay the last range, and there is no throughput extrapolation. Range responses must
match the requested offset and declared total size. A server that ignores a resumed
single GET restarts from zero; ignored ranges in a parallel download are rejected.
The complete archive must still pass its original size and SHA256 checks.
Integrity failures, denied requests and other HTTP errors are not retried.

Cold preparations share a 60-second deadline across grants, admission,
materialization and downloading rather than rejecting an ordinary burst
immediately. Each network read uses the remaining budget. The HTTP server
bounds concurrent requests; two admission slots bound preparation waiters.
The existing host ingress blocks vLLM's administrative load/unload endpoints.
The resolver is installed as a standard `vllm.general_plugins` entry point and
selected by the LoRA launcher; disabled deployments do not register it.

The metadata source is `TaskVersion`, not a separate hosting record. The private
grant request is `{workspace_id, version_name}`; its response composes
`{workspace_id, version: TaskVersion, download: AdapterDownload}`. Signed URLs are
not persisted on task versions. The production list is
`{data: [{workspace_id, version_name}]}`, filtered by base model. These private
routes are provided by the API; the gateway resolves private selectors within the
authenticated workspace before dispatch.

Version slugs are unique within a workspace and are not renameable. They are model
identifiers, never filesystem paths. Disk directories use `<version UUID>-<SHA256>`
cache keys; grants return the existing immutable metadata used to verify downloads.
There is no `ft-` model-name prefix or checksum in the serving name.

Set `GRADIATED_API_BASE_URL` to the API origin, for example
`https://api.gradiated.com` in production or `http://127.0.0.1:3001` locally.
The loader derives both private endpoint paths. HTTP is accepted only for loopback
hosts; other destinations require HTTPS. Hosts reuse their existing per-host certificate-renewal bearer credential and send
`X-Gradiated-Instance-Id` and `X-Gradiated-Nomad-Node-Id` identity headers. The API
checks the enrolled node and revocation/retirement state using the existing host
credential store. There is no LoRA-specific shared secret. Private routes are
registered when the existing host authentication dependencies are configured.
Grant responses use `no-store`
and reuse the existing five-minute, versioned S3 signing path. Hosts still enforce
their exact download hostname allowlist.

The startup list includes at most 4096 available current production versions per
base, ordered by the task's last update, with no signed URLs. Each host fetches a
grant only when preparing an adapter. Archived workspaces and suspended
organizations are excluded. Qualification candidates may obtain a grant while
their version remains unavailable; preparing one does not make it production.

## Cache ownership

| Tier            | Owner                     | Behavior                                      |
| --------------- | ------------------------- | --------------------------------------------- |
| S3 archive      | Training artifact storage | Durable source                                |
| Allocation disk | Loader                    | Verified paths retained once returned to vLLM |
| CPU tensors     | vLLM                      | Native LRU, bounded by `--max-cpu-loras`      |
| GPU slots       | vLLM                      | Native LRU, bounded by `--max-loras`          |

There is no loader CPU byte budget or CPU/GPU residency bookkeeping. Host RAM and
GPU memory still need qualification for the chosen native counts, ranks and TP.

Returned paths stay available for the allocation's entire engine lifetime:
vLLM may reload a CPU-evicted adapter directly from its retained path without
calling our loader. Disk LRU therefore evicts only files not returned to vLLM, including
recovered files after a task restart. If pinned files fill the disk budget,
new preparations return a capacity error; base and registered-adapter serving
continue. There is no attempt to unload adapters to free disk. Size disk storage
for the expected lifetime working set rather than just the CPU working set. The
production GLM allocation budgets 256 GiB for adapters and reserves 350000 MiB
of local disk for the cache plus runtime bundle. Each allocation has its own
cache, including when TP2 and TP4 deployments share a node. Native GPU/CPU
limits remain 8/64 adapters, with maximum rank 8. A measured full-layer rank-2
artifact uses about 38 MiB on disk, including its retained archive; this is a
working-set estimate for that artifact, not a bound for every model or rank.
Pinned-disk alerts indicate that a new allocation with fresh cache capacity may
be needed; CPU or GPU eviction cannot release those retained paths.

Materialization is serialized per allocation, with at most two preparation callers
admitted. Additional callers wait within the shared 60-second preparation deadline. Reservations include the archive, extracted files and manifest.
Writes use a staging directory and atomic rename. Restart removes incomplete
staging directories, revalidates recovered files when used and starts with no
acknowledged registrations. Returned paths remain pinned even if native registration
fails or a request is cancelled, because vLLM may retain them. Startup preload
retries check vLLM's model list after an uncertain registration. Adapter failures
leave base readiness available; engine health/restarts remain with the existing
warmup supervisor, Desmond and Nomad.

After base warmup qualifies, each allocation independently preloads production
versions in the background, up to its native CPU adapter count or startup deadline.
An empty list loads nothing. A metadata outage logs a bounded error and permits
on-demand preparation. `LORA_PRELOAD_SECONDS` defaults to 600 and is checked between
bounded preparations. There is no placement or spreading across allocations.

## Configuration

TP and base revision come from the existing vLLM command; layer/expert geometry
comes from the pinned model configuration, including nested `text_config`.
A qualified deployment may set `lora_base_model_revision` in its existing release
and `LORA_BASE_MODEL_REVISION` for the loader when training and serving use distinct
checkpoint revisions (for example BF16 training and FP8 serving). Without that
setting, the serving revision is required. This is an explicit qualified pairing,
not an automatic quantization conversion or acceptance of arbitrary revisions.
Task versions retain their actual training revision. Keep LoRA disabled until the
pairing's model/tokenizer/adapter layout and inference have been verified.

Nomad's `tensor_parallel_size` controls both GPU allocation and the engine flag;
the assigned GPU UUID count must match. These are host decisions, not adapter fields.

| Setting                  | Source/default                                                   |
| ------------------------ | ---------------------------------------------------------------- |
| `LORA_ENABLED`           | Nomad `lora_enabled`, false                                      |
| `MODEL_ID`               | Existing public base model ID                                    |
| `LORA_GPU_SLOTS`         | Native `max_loras`, 8                                            |
| `LORA_CPU_SLOTS`         | Native `max_cpu_loras`, 64; at least GPU slots                   |
| `LORA_MAX_RANK`          | Native `max_lora_rank`, 8                                        |
| `LORA_DISK_CACHE_BYTES`  | Explicit allocation disk budget; zero fails startup when enabled |
| `LORA_DOWNLOAD_HOSTS`    | Exact S3 HTTPS host allowlist                                    |
| `GRADIATED_API_BASE_URL` | API origin; HTTPS or local loopback HTTP                         |
| `HOST_IDENTITY_FILE`     | `/etc/gradiated/host-identity.json`                              |
| `LORA_CACHE_DIR`         | `${NOMAD_ALLOC_DIR}/lora`                                        |
| `ADAPTER_PORT`           | Allocation-local control port; inference stays on `RUNTIME_PORT` |

Host bootstrap copies the existing certificate-renewal identity into
`/etc/gradiated/host-identity.json`, owned by `runtime` with mode 0600; it contains
only instance/node identity and the existing bearer credential, not a TLS private
key. Existing enrolled hosts need the same copy installed before enabling LoRA;
this does not require reenrollment or restarting provider pods. Revoking the host
credential also denies subsequent adapter grants and startup lists.

Prepare/probe/status/metrics bind only to loopback and use the existing
bearer-authenticated host ingress for external access, like the native vLLM
runtime. Prepare/probe/resolve take `{name, workspace_id}`, where `name` is the exact
version slug. Probe checks a bounded generation's
returned identity and usage.
Metrics live at `/internal/adapters/metrics`; they report file hits, downloads,
startup registrations, failures, disk evictions and preparation duration with no adapter or
workspace labels. Prometheus discovers enabled allocations from the worker's internal
`GET /metrics/targets/lora` endpoint and scrapes the existing authenticated host
`/alloc/<id>/internal/adapters/metrics` route. Discovery reads the deployment
inventory every thirty seconds; it is not part of inference or placement. The
scrape uses the same runtime bearer credential as the gateway. Disabled and
draining allocations are excluded. Discovery failures return 503, preserving
Prometheus's last successful target list rather than silently returning no targets.

Operation counters and the general failure counter cover grant, file and native
startup-registration failures; timestamps detect failures before the first scrape.
Failure logs include the exception type and upstream HTTP status when available,
without exception messages, response bodies or URLs. Disk gauges expose the limit
and bytes pinned for native reloads. Alerts cover failed/missing loader scrapes,
recent operation/capacity failures and sustained pinned disk pressure. The
[LoRA dashboard](https://grafana.gradiated.com/d/gradiated-lora) links to Nomad
allocation logs. Gateway failures remain in the central Loki diagnostics.

`lora_operation` JSON logs report action, outcome and elapsed seconds. Successes
are informational and failures are warnings. Failure logs omit exception text,
prompts, adapter/workspace identifiers, signed URLs and tokens. Inspect the
allocation's `vllm` task logs alongside gateway/runtime errors. Native inference
failures remain covered by the existing gateway alerts; loader metrics do not
claim to measure native CPU/GPU residency.

PEFT archives may be flat or under `adapter/`, with `adapter_config.json`,
`adapter_model.safetensors` and optional `README.md`. BF16/F16/F32 and complete
per-expert 2D or fused 3D layouts are accepted; vLLM's format flag comes from tensors.
Links, traversal, executable files and unsupported PEFT features are rejected.
vLLM owns model-specific module compatibility. This does not qualify vision-tower
adapters or GLM numeric correctness.

## Verification

```sh
python3 -m unittest discover -s product/inference/lora -p 'test_*.py'
uv tool run ruff@0.16.10 check product/inference/lora
uv tool run ruff@0.16.10 format --check product/inference/lora
```

Synthetic/local HTTP tests cover registration, coalescing, archive integrity,
workspace checks, pinned-file safety, disk admission, recovery, startup and the
absence of inference proxy routes. Resolver tests cover cold loading, disk reuse,
workspace/version failures and the preload/resolution race. Bundle verification
requires the pinned vLLM resolver interface, plugin discovery and native per-name
coalescing to pass; local tests skip that native check when vLLM is absent. The real Nomad/NGINX fixture checks direct
completion routing, private control routing and blocked admin endpoints. CI also
runs loader tests inside the pinned GLM bundle. Real-artifact/reference, native
CPU/GPU eviction and reload, KV/cancellation isolation, latency and colocated
TP2/TP4 memory checks are release gates. The pinned GLM runtime and actual trained
rank-two adapter passed these checks on B300, including all MLA layers in prefill
and decode against independent same-input FP32 math; see [GLM qualification](../runtimes/glm/README.md).
Absolute whole-model logprob tolerance also failed on the LoRA-disabled control,
so these checks do not establish task quality or bitwise whole-model determinism.
