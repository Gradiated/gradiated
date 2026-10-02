# vLLM adapter loading

The GLM bundle includes an opt-in adapter loader. It is a control service, not an
inference proxy. Completion requests, streaming, cancellation, batching and CPU/GPU
adapter caching remain with vLLM. `lora_enabled` defaults to false while the private
metadata API and gateway integration are completed in PRs 3 and 4.

## Request path

The gateway authorizes an exact task version in its workspace and derives
`ft-<version UUID>-<full SHA256>`. Before dispatching it calls the allocation's
`POST /internal/adapters/prepare` with `{name, workspace_id}` through the existing authenticated host ingress. The loader:

1. Obtains existing task-version metadata and a short-lived download grant.
2. Reuses verified local files or downloads the S3 archive into a staging directory.
3. Verifies size/checksum, safe archive contents, base revision, rank, layer coverage
   and expert completeness.
4. Calls vLLM's loopback-only `/v1/load_lora_adapter` with the immutable name and
   local path. Subsequent preparations reuse the acknowledged registration.

The gateway then dispatches directly to the allocation's vLLM runtime port using
that name. The loader never forwards completions, reads token streams, holds
inference slots, tracks active requests, unloads adapters or restarts the engine.
The existing host ingress blocks vLLM's administrative load/unload endpoints and
routes only the loader's private control paths to its separate loopback port.

The metadata source is `TaskVersion`, not a separate hosting record. The private
grant request is `{workspace_id, version_id, sha256}`; its response composes
`{workspace_id, version: TaskVersion, download: AdapterDownload}`. Signed URLs are
not persisted on task versions. The production list is
`{data: [{workspace_id, version_id, sha256}]}`, filtered by base model. These private
routes are provided by the API; workspace authorization at the gateway follows in PR 4.

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

| Tier            | Owner                     | Behavior                                        |
| --------------- | ------------------------- | ----------------------------------------------- |
| S3 archive      | Training artifact storage | Durable source                                  |
| Allocation disk | Loader                    | Verified files retained for registered adapters |
| CPU tensors     | vLLM                      | Native LRU, bounded by `--max-cpu-loras`        |
| GPU slots       | vLLM                      | Native LRU, bounded by `--max-loras`            |

There is no loader CPU byte budget or CPU/GPU residency bookkeeping. Host RAM and
GPU memory still need qualification for the chosen native counts, ranks and TP.

Registered paths stay available for the allocation's entire engine lifetime:
vLLM may reload a CPU-evicted adapter directly from its retained path without
calling our loader. Disk LRU therefore evicts only unregistered files, including
recovered files after a task restart. If registered files fill the disk budget,
new preparations return a capacity error; base and registered-adapter serving
continue. There is no attempt to unload adapters to free disk. Size disk storage
for the expected lifetime working set rather than just the CPU working set.

Materialization is serialized per allocation, with at most two preparation callers
waiting/loading. Reservations include the archive, extracted files and manifest.
Writes use a staging directory and atomic rename. Restart removes incomplete
staging directories, revalidates recovered files when used and starts with no
acknowledged registrations. An uncertain registration keeps files pinned; retries
check vLLM's registered model list before attempting another load. Adapter failures
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
runtime. Probe takes `{name, workspace_id}` and checks a bounded generation's
returned identity and usage.
Metrics live at `/internal/adapters/metrics`; they report file hits, downloads,
registrations, failures, disk evictions and preparation duration with no adapter or
workspace labels. Failure logs omit exception text, prompts, signed URLs and tokens.

PEFT archives may be flat or under `adapter/`, with `adapter_config.json`,
`adapter_model.safetensors` and optional `README.md`. BF16/F16/F32 and complete
per-expert 2D or fused 3D layouts are accepted; vLLM's format flag comes from tensors.
Links, traversal, executable files and unsupported PEFT features are rejected.
vLLM owns model-specific module compatibility. This does not qualify vision-tower
adapters or GLM numeric correctness.

## Verification

```sh
python3 -m unittest discover -s product/inference/lora -p 'test_*.py'
uv tool run ruff check product/inference/lora
uv tool run ruff format --check product/inference/lora
```

Synthetic/local HTTP tests cover registration, coalescing, archive integrity,
workspace checks, pinned-file safety, disk admission, recovery, startup and the
absence of inference proxy routes. The real Nomad/NGINX fixture checks direct
completion routing, private control routing and blocked admin endpoints. CI also
runs loader tests inside the pinned GLM bundle. Real-artifact/reference, native
CPU/GPU eviction and reload, KV/cancellation isolation, latency and colocated
TP2/TP4 memory checks remain gates before enabling production.
