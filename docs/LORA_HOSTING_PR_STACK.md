# LoRA hosting implementation stack

The stack builds on the existing pinned vLLM bundles, Nomad allocations,
TypeScript API/worker, Rust gateway and console. Adapter hosting is opt-in.
Production enabling and live GPU qualification require separate authorization.

| PR  | Branch                        | Scope                                                                                |
| --- | ----------------------------- | ------------------------------------------------------------------------------------ |
| 1   | `feat/lora-hosting-contracts` | Base revision metadata on existing task versions and derived immutable runtime names |
| 2   | `feat/lora-vllm-runtime`      | Verified artifacts, local disk files, preparation and native vLLM cache integration  |
| 3   | `feat/lora-hosting-control`   | Private artifact grants, candidate validation and the existing production pointer    |
| 4   | `feat/lora-private-inference` | Scoped gateway resolution, exact dispatch, release identity and console actions      |

PRs 1 and 2 and the planning documents are merged into `main` via PR #360.
PR 3 targets `main`; later dependent work targets its predecessor while stacked.
Review runtime/cache safety before private inference.

PR 2's [runtime implementation](../product/inference/lora/README.md)
adds opt-in GLM bundle support, host-local caches and private preparation. The
existing deployment release advertises `lora_enabled` only when enabled. Private
grant/list routes are implemented in PR 3 and gateway dispatch follows in PR 4; keep
hosting disabled until those and real GPU qualification are complete.

PR 3 adds authenticated private metadata/download grants and a bounded startup
list using the existing S3 signer and task production pointer. Archived workspaces
and suspended organizations are excluded. The list includes at most 4096 available
current versions per base, ordered by the task's last update. Grant requests bind
workspace, version and full artifact checksum; candidates can be prepared before
they are available for production. Grants do not change eligibility or promotion.
Publishing records the base revision from the frozen training manifest. Legacy
artifacts without that revision remain downloadable through the existing public
management route but cannot be loaded or promoted. Existing eligibility remains
required for promotion; this PR does not automatically qualify trained versions.

Existing task/version records are the source of truth. There are no new hosting
or promotion tables, hosting workflow, reconciliation loop or fleet service.
At startup, each allocation preloads compatible current task production versions
up to its cache limits and a bounded startup deadline. Each allocation does this
independently; there is no adapter placement or spreading across hosts. During
its lifetime, adapters load on demand; vLLM owns CPU/GPU LRU and request lifetimes.
Base readiness opens after base warmup and preloading continues in the background.
An empty production list loads no adapters. The loader is a control service;
inference and streams go directly through the existing ingress to vLLM.

The hierarchy is immutable S3 artifacts, verified allocation-local files, native
vLLM CPU tensors and native GPU slots. CPU adapter count and GPU slots are engine
settings; there is no custom CPU byte budget, CPU eviction or active-stream tracking.
Registered disk paths remain available for the engine lifetime so vLLM can reload
CPU-evicted adapters. Disk LRU only removes unregistered files. Registered files
filling the disk budget reject new preparations without disrupting existing serving.
After restart, recovered disk files can be revalidated/reused and registrations
are rebuilt. Concurrent preparations share one materialization/registration.

Existing gateway billing/concurrency and vLLM scheduling remain authoritative.
The loader owns authorized metadata, verification, local materialization and native
registration, never completion forwarding or runtime cache eviction.
Immutable names contain a version UUID and full artifact checksum. Runtime
configuration pins base/tokenizer/runtime compatibility, TP geometry,
module/layer coverage, rank and cache limits. Inference uses the existing base
catalog capabilities and prices. Configuration may only enable qualified runtimes.

Reuse existing base-model deployment configuration for TP and runtime settings;
add cache settings locally where consumed. These are not adapter attributes or a
new shared host-profile schema. Artifact metadata comes from `TaskVersionSchema`
and `TaskVersionAdapterSchema`, rather than a separate preparation model. Workspace
ownership comes from the task. Runtime names are derived from the version ID and
artifact checksum, not stored separately. Private artifact access will reuse the
existing signing path and `AdapterDownloadSchema` for temporary download grants;
signed URLs are not persisted on versions. The loader checks version metadata against its local runtime before
loading. Existing artifacts without a recorded base revision remain readable,
but serving requires a verified base revision. Architecture-specific module/layer
geometry is qualified against real artifacts.

Private selectors are `ft/<version_uuid>` and `tasks/<task_uuid>/production`,
authorized and cached by workspace. Resolve production once; ongoing streams and
retries retain the exact version. Base health and combined adapter served identity
remain separate. Private versions stay out of global discovery. The task capture
header does not select an adapter.

The [hosting proposal](TASK_FINE_TUNING_FROM_TRACES_PLAN.md#proposed-hosting-and-production-promotion)
is the broader design. This initial stack supersedes its separate hosting-workflow
and distributed allocation-lease suggestions, and its additional hosting/audit
tables. Qwen checks do not qualify GLM all-layer/expert adapters. TP2 and TP4 need
independent qualification. Budgets include all allocations, staging, replication,
tmpfs and restart overlap.

Run DevEx first, then narrow contracts, PostgreSQL, runtime, API/worker, Rust and
console checks. Cover corrupted/hostile archives, coalesced loads, cache pressure,
registered-file retention, restart, workspace isolation, concurrent promotion and streaming
cancellation. Before enabling production, execute separately
bounded real-artifact reference, KV isolation, TP2/TP4 co-location, latency under
contention and fault-domain recovery checks. CPU doubles establish control
behavior only; numeric limits, pricing and quality gates require qualified inputs.
