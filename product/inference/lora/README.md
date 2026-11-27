# SGLang adapter loading

The SGLang bundles (GLM-5.3 Flash and DeepSeek V4.1 Flash 1017) include an opt-in
adapter loader. It is a control service, not an inference proxy. Completion
requests, streaming, cancellation, batching and CPU/GPU adapter caching remain
with SGLang. The private metadata API and gateway integration are implemented.
`lora_enabled` defaults to false in the job template. A production release enables
it with an independently qualified training/serving revision pair, for example
BF16 GLM training and NVFP4 GLM serving.

DeepSeek's declared targets include the top-level `lm_head`. The external upload API accepts the same canonical head keys and validates the vocabulary and hidden dimensions against the pinned DeepSeek configuration; other architectures do not gain head support. Head adapters use
`base_model.model.lm_head.lora_A.weight` and `lora_B.weight` (or bare `lm_head`
keys), declare `target_modules: ["lm_head"]`, and require the host's engine target
allowlist to include it. A must have shape `[rank, hidden_size]` and B
`[vocab_size, rank]` from the pinned model config. Layer-local heads, added
vocabulary, transposed factors and RSLoRA heads are rejected. Admission also
rechecks the host allowlist when recovering a verified disk cache.

This admission path does not qualify an adapter for serving. Active head LoRA
still requires the pinned runtime's TP sharding, CUDA graphs, speculative
decoding, adapter isolation and behavioral checks. Separate LoRA residuals can
round differently from a BF16 merged checkpoint; merged-model results alone
do not establish active-adapter equivalence.

## Request path

The gateway authorizes an exact task version in its workspace and sends a normal
inference request with the internal model name
`<workspace UUID>/<version UUID>`. Public requests still use the
existing version or task production slug. The gateway does not prepare adapters.

SMG forwards the unknown model name to the allocation's single SGLang worker
(`SMG_ROUTE_UNKNOWN_MODELS=1`, a bundle patch). With `SGLANG_LORA_RESOLVER_URL`
set, SGLang treats any model name other than its served name as an adapter, and
on first use its resolver hook (a bundle patch to the tokenizer manager) calls
the allocation's loopback `POST /internal/adapters/resolve` with
`{name, workspace_id}`. The loader:

1. Obtains existing task-version metadata and a short-lived download grant.
2. Reuses verified local files or downloads the S3 archive into a staging directory.
3. Verifies size/checksum, safe archive contents, base revision, rank, layer range
   and expert completeness.
4. Returns the retained local path, without calling SGLang.

The hook then loads the path through SGLang's native `load_lora_adapter`, which
assigns the adapter ID and registers it; concurrent requests for one name share a
single resolution. Registered adapters use SGLang's native CPU/GPU slots. The hook
runs the blocking file request on a worker thread, so downloading does not block
the SGLang API event loop. Names that are not `<workspace UUID>/<version UUID>` and all
resolution errors fail closed with a bounded message; they never fall back to the
base model.

The loader never forwards completions, reads token streams, holds inference slots,
tracks active requests, unloads adapters or restarts the engine. Startup preload
and qualification retain the native load API. Materialization locks are released
before calls into SGLang, allowing concurrent native resolution without deadlock.
Archives of at least 8 MiB use at most eight equal, non-overlapping ranges, all
started together and written into one staging file; smaller archives use a single
GET. Each range has at most twelve attempts, capped at five seconds and the
original cold deadline. Timeouts, DNS lookup failures, connection resets and HTTP/TLS early EOF resume
from bytes already written; DNS and connection retries pause for up to one second
within that deadline. Queued
chunks cannot delay the last range, and there is no throughput extrapolation. Range responses must
match the requested offset and declared total size. A server that ignores a resumed
single GET restarts from zero; ignored ranges in a parallel download are rejected.
The complete archive must still pass its original size and SHA256 checks.
Integrity failures, denied requests and other HTTP errors are not retried.

Cold preparations share a 60-second deadline across grants, admission,
materialization and downloading rather than rejecting an ordinary burst
immediately. Each network read uses the remaining budget. The HTTP server
bounds concurrent requests; two admission slots bound preparation waiters.
SGLang's administrative load/unload endpoints listen only on the private backend
port, which the host ingress does not route; SMG does not proxy them. Disabled
deployments set neither environment variable, so their engines never resolve
adapter names.

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

Production runtimes use `GRADIATED_API_BASE_URL=http://127.0.0.1:3004`.
That loopback bridge forwards over Tailscale to the private GPU control listener.
The local mprocs API starts the same listener on port 3005, leaving the collector
on 3004; local LoRA uses `http://127.0.0.1:3005`. These are the only supported
artifact API origins. GPU hosts have no database credentials or host bearer token
for artifact grants. Tailscale grants restrict GPU access to the private listener.

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
| Allocation disk | Loader                    | Verified paths retained once returned to SGLang |
| CPU tensors     | SGLang                    | Native LRU, bounded by `--max-loaded-loras`     |
| GPU slots       | SGLang                    | Native LRU, bounded by `--max-loras-per-batch`  |

There is no loader CPU byte budget or CPU/GPU residency bookkeeping. Host RAM and
GPU memory still need qualification for the chosen native counts, ranks and TP.

Returned paths stay available for the allocation's entire engine lifetime:
SGLang reloads an evicted adapter directly from its retained path without
calling our loader. Disk LRU therefore evicts only files not returned to SGLang, including
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
fails or a request is cancelled, because SGLang may retain them. Startup preload
retries check SGLang's model list after an uncertain registration. Adapter failures
leave base readiness available; engine health/restarts remain with the existing
warmup supervisor, Desmond and Kubernetes.

After base warmup qualifies, each allocation independently preloads production
versions in the background, up to its native CPU adapter count or startup deadline.
An empty list loads nothing. A metadata outage logs a bounded error and permits
on-demand preparation. `LORA_PRELOAD_SECONDS` defaults to 600 and is checked between
bounded preparations. There is no placement or spreading across allocations.

## Configuration

TP and base revision come from the runtime configuration; layer/expert geometry
comes from the pinned model configuration, including nested `text_config`.
A qualified deployment may set `lora_base_model_revision` in its existing release
and `LORA_BASE_MODEL_REVISION` for the loader when training and serving use distinct
checkpoint revisions (for example BF16 training and FP8 serving). Without that
setting, the serving revision is required. This is an explicit qualified pairing,
not an automatic quantization conversion or acceptance of arbitrary revisions.
Task versions retain their actual training revision. Keep LoRA disabled until the
pairing's model/tokenizer/adapter layout and inference have been verified.

The pinned runtime profile controls both GPU allocation and the engine flag;
the assigned GPU UUID count must match. These are host decisions, not adapter fields.

| Setting                  | Source/default                                                                                                                                   |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `LORA_ENABLED`           | Runtime catalogue `lora_enabled`, false                                                                                                          |
| Cartridge pool           | DeepSeek only: 4 GiB per rank (`CARTRIDGE_POOL_BYTES` in its `config.py`) whenever `LORA_ENABLED`; release `cartridge_enabled` routes cartridges |
| `MODEL_ID`               | Existing public base model ID                                                                                                                    |
| `LORA_GPU_SLOTS`         | Native `max_loras`, 8                                                                                                                            |
| `LORA_CPU_SLOTS`         | Native `max_cpu_loras`, 64; at least GPU slots                                                                                                   |
| `LORA_MAX_RANK`          | Native `max_lora_rank`, 8                                                                                                                        |
| `LORA_DISK_CACHE_BYTES`  | Explicit allocation disk budget; zero fails startup when enabled                                                                                 |
| `LORA_DOWNLOAD_HOSTS`    | Exact S3 HTTPS host allowlist                                                                                                                    |
| `GRADIATED_API_BASE_URL` | API origin; HTTPS or local loopback HTTP                                                                                                         |
| `LORA_CACHE_DIR`         | `${GRADIATED_RUNTIME_DIR}/lora`                                                                                                                  |
| `ADAPTER_PORT`           | Allocation-local control port; inference stays on `RUNTIME_PORT`                                                                                 |

Prepare/probe/status/metrics bind only to loopback and use the existing
Tailscale host ingress for external access, like the native SGLang
runtime. Prepare/probe/resolve take `{name, workspace_id}`, where `name` is the
version ID. Probe checks a bounded generation's returned identity and usage. The
API calls probe through the host proxy (`<service_url>/internal/adapters/probe`)
when an editor promotes an unavailable version, such as an upload; a pass makes
the version available and production (see the
[serving contract](../../../docs/TASK_FINE_TUNING_SERVING_CONTRACT.md)).
A cartridge is probed on every promotion, and only on `cartridge_enabled`
deployments. Its probe also sends a fixed canary prompt with and without the
cartridge, at temperature 0 with the top 20 logprobs. It passes only if a
next-token distribution, compared while the two greedy outputs still agree,
differs by more than 0.02 total variation, or if the greedy tokens differ.
Otherwise it answers 422 `cartridge_not_applied`.
Metrics live at `/internal/adapters/metrics`; they report file hits, downloads,
startup registrations, failures, disk evictions and preparation duration with no adapter or
workspace labels. Prometheus discovers enabled allocations from the worker's internal
`GET /metrics/targets/lora` endpoint and scrapes the private host
`/alloc/<id>/internal/adapters/metrics` route. Discovery reads the deployment
inventory every thirty seconds; it is not part of inference or placement. The scrape uses the private Tailscale route. Disabled and
draining allocations are excluded. Discovery failures return 503, preserving
Prometheus's last successful target list rather than silently returning no targets.

Operation counters and the general failure counter cover grant, file and native
startup-registration failures; timestamps detect failures before the first scrape.
Failure logs include the exception type and upstream HTTP status when available,
without exception messages, response bodies or URLs. Disk gauges expose the limit
and bytes pinned for native reloads. Alerts cover failed/missing loader scrapes,
recent operation/capacity failures and sustained pinned disk pressure. The
[LoRA dashboard](https://grafana.gradiated.com/d/gradiated-lora) links to Kubernetes
allocation logs. Gateway failures remain in the central Loki diagnostics.

`lora_operation` JSON logs report action, outcome and elapsed seconds. Successes
are informational and failures are warnings. Failure logs omit exception text,
prompts, adapter/workspace identifiers, signed URLs and tokens. Inspect the
allocation's runtime logs alongside gateway errors. Native inference
failures remain covered by the existing gateway alerts; loader metrics do not
claim to measure native CPU/GPU residency.

PEFT archives may be flat or under `adapter/`, with `adapter_config.json`,
`adapter_model.safetensors` and optional `README.md`. BF16/F16/F32 and complete
per-expert 2D or fused 3D layouts are accepted by the loader.
Links, traversal, executable files and unsupported PEFT features are rejected.
SGLang owns model-specific module compatibility and rejects adapters for
modules outside the runtime's `--lora-target-modules`. This does not qualify vision-tower
adapters or GLM numeric correctness.

Cartridge versions (`format: "cartridge"`, see the
[cartridge plan](../../../docs/CARTRIDGE_SERVING_PLAN.md)) download one
`cartridge.safetensors` file rather than an archive. Before the file is
retained, the loader checks its size and SHA256 and parses the header as JSON,
never pickle. It also checks the tensor names, dtypes, shapes and byte ranges
against the task version and the pinned `hidden_size`, `vocab_size` and
`max_position_embeddings`. The embeddings must be finite and the slot IDs
inside the vocabulary. Resolution returns
`{kind: "cartridge", path, sha256, num_tokens}`. SGLang reads the file into its
cartridge table, so cartridges are never registered through `load_lora_adapter`.

Versions published from grad artifacts (`adapter.source.kind: "grad"`) point at
the artifact's `grad.artifact/1` bundle in the training bucket, read in place:
`artifacts/<workspace>/<sha256>.grad.tar.gz`, where `sha256` and `size_bytes`
describe the bundle. Both formats then download the bundle, extract only
`manifest.json`, the optional `eval_report.json` and the format's files at the
bundle root, and check each file against `manifest.files` before the format
checks above run. The envelope files are deleted after that check. The bundle's
S3 host must be in `LORA_DOWNLOAD_HOSTS`.

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
runs these tests inside the pinned SGLang bundle. The NGINX fixture checks direct
completion routing, private control routing and blocked admin endpoints. CI also
runs loader tests inside the pinned GLM bundle. Real-artifact/reference, native
CPU/GPU eviction and reload, KV/cancellation isolation, latency and colocated
TP2/TP4 memory checks are release gates. The pinned GLM runtime and actual trained
rank-two adapter passed these checks on B300, including all MLA layers in prefill
and decode against independent same-input FP32 math; see [GLM qualification](../runtimes/glm/README.md).
Absolute whole-model logprob tolerance also failed on the LoRA-disabled control,
so these checks do not establish task quality or bitwise whole-model determinism.

A fresh full-layer rank-2 GLM adapter also passed the production gateway path after
training, checkpoint recovery, verification and publication. Eight simultaneous
cold requests shared one download and completed in about 8.3 seconds. A 270-request
public soak at concurrency 8 passed streaming, cancellation, promotion and historical
version checks without failures. Native CPU/GPU cache pressure passed 136 requests
at concurrency 32 across 65 names with 8 GPU and 64 CPU slots, followed by clean
unloading and successful base and canonical-adapter requests. These are measured
serving reliability checks on B300, not task-quality or general latency guarantees.
