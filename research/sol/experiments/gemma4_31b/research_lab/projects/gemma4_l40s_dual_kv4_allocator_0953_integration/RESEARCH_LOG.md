## 2026-07-27 — fixed dual-KV4 allocator composition

Question: can the unchanged local D256 KV4+O4 and global
D512 recent-E5M2/old-KV4+O8 paths compose under the sole `0.953` split with
complete ownership and a positive exact-c32 L40S memory interval?

Action: reconstructed the ledger from direct-hashed inputs, correcting the
prior 20,480-byte half-sentinel undercount; implemented one fixed pool
configurator, canonical allocator release/move hooks, local producer/consumer
routing, and an all-global-payload transition barrier before the first global
consumer. Materialized every admitted
kernel, adapter, workload, and consumer byte in this project. Ran eight
focused behavioral checks and syntax/compile checks; no CUDA or endpoint ran.

Evidence: `L40S_DUAL_KV4_ALLOCATOR_0953_OFFLINE_TERMINAL.json` reports static
and conservative physical margin `1,579,875,259..2,547,378,835` bytes.
Assigned context, graph, and workspace bounds leave
`159,262,703..180,737,540` dynamic bytes, while the complete adverse ledger
charges all remaining scheduler/fragmentation state to the reserve and
therefore reports dynamic margin `0..180,737,540`. The terminal contains the
full symbolic component/endpoint inequality and no transferred latency.

Interpretation: the fixed composition is offline source-complete and
memory-positive. It does not establish target compile, latency, endpoint
performance, or quality. The fresh coordinator import was typed
non-executable because the selected clean source snapshot is intentionally
partial; its diagnostic is durable and the 4.5-GiB temporary cache was fully
removed.

Next: import the in-flight local result without replay, measure one global
complete pair, and launch the single project-local current-runtime command
only if their margins support the terminal inequality.
