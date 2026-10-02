# LoRA hosting implementation stack

The stack builds on the existing pinned vLLM bundles, Nomad allocations,
TypeScript API/worker, Rust gateway and console. Adapter hosting is opt-in.
Production enabling and live GPU qualification require separate authorization.

| PR | Branch | Scope |
| --- | --- | --- |
| 1 | `feat/lora-hosting-contracts` | Immutable adapter identity and runtime compatibility/cache configuration |
| 2 | `feat/lora-vllm-runtime` | Verified PEFT loading, bounded caches, preparation, per-allocation admission and streaming |
| 3 | `feat/lora-hosting-control` | Private artifact grants, candidate validation and the existing production pointer |
| 4 | `feat/lora-private-inference` | Scoped gateway resolution, exact dispatch, release identity and console actions |

Each branch targets its predecessor while stacked. Review identity/contracts
before dependent interfaces and runtime/cache safety before private inference.
The existing planning PR is the prerequisite.

Existing task/version records are the source of truth. There are no new hosting
or promotion tables, hosting workflow, reconciliation loop or fleet service.
Adapters load on demand into a per-allocation LRU; restarts recover lazily. Each runtime
controller enforces a single allocation-wide capacity limit across base and
adapter requests, rather than adding distributed GPU leases. Existing gateway
organization billing/concurrency admission remains intact.

vLLM owns CPU tensors and GPU scheduling. The controller owns verified local
materialization, coalesced loading and active references for safe eviction.
Immutable names contain a version UUID and full artifact checksum. Runtime configuration pins base/tokenizer/runtime compatibility, TP geometry,
module/layer coverage, rank and cache limits. Inference uses the existing base
catalog capabilities and prices. Configuration may only enable qualified runtimes.

Private selectors are `ft/<version_uuid>` and `tasks/<task_uuid>/production`,
authorized and cached by workspace. Resolve production once; ongoing streams and
retries retain the exact version. Base health and combined adapter served identity
remain separate. Private versions stay out of global discovery. The task capture
header does not select an adapter.

The [hosting proposal](TASK_FINE_TUNING_FROM_TRACES_PLAN.md#proposed-hosting-and-production-promotion)
is the broader design. This initial stack supersedes its separate hosting-workflow
and distributed allocation-lease suggestions, and its additional hosting/audit
tables. Qwen checks do not qualify GLM
all-layer/expert adapters. TP2 and TP4 need independent qualification. Budgets
include all allocations, staging, replication, tmpfs and restart overlap.

Run DevEx first, then narrow contracts, PostgreSQL, runtime, API/worker, Rust and
console checks. Cover corrupted/hostile archives, coalesced loads, cache pressure,
active eviction, restart, workspace isolation, concurrent promotion and streaming cancellation. Before enabling production, execute separately
bounded real-artifact reference, KV isolation, TP2/TP4 co-location, latency under
contention and fault-domain recovery checks. CPU doubles establish control
behavior only; numeric limits, pricing and quality gates require qualified inputs.
