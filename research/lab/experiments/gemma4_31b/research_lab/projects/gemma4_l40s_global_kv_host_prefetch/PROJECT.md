# L40S global-KV host-prefetch economics

## Question

Can one deterministic layer-ahead pinned-host prefetch policy keep Gemma 4's
global E5M2 KV cache off the L40S while preserving exact attention semantics,
freeing useful device memory without pushing the exact c32 workload above the
price-normalized `1.4776251501079425 s/request` boundary?

## Why this changes the portfolio

The fixed local KV4-plus-outlier representation targets local-cache capacity,
but the exact c32 accounting still assigns `5,311,979,520` device bytes to the
10 global E5M2 layers. Global attention consumes full history and may turn a
nominal residency saving into compulsory PCIe traffic on every decode step.
That transfer lower bound can be decided from exact model/workload geometry,
the current runtime ownership path, and a single explicit double-buffer
schedule without GPU spend.

A positive complete overlap bound would expose a materially different L40S
placement route. A transfer-bound negative would close host-resident global KV
for this workload and prevent later allocator experiments from treating those
bytes as cheaply removable.

## Bound scope

- Exact model and revision from `CAMPAIGN.md`
- Exact c32 workload: 4,214 prompt tokens, 358 output tokens, 535 shared-prefix
  tokens, page size 1, TP1
- Ten global layers remain E5M2 and mathematically unchanged
- All local layers remain on-device under the existing local-KV representation
- One policy only: pinned-host global KV with two device staging buffers and
  deterministic layer-ahead asynchronous prefetch on one transfer stream
- Source/runtime identity: official SGLang commit
  `c6a6200a1a778a799ba61c395ac292317f01ebc9`

Use the current accelerator inventory for stable PCIe/device facts and bind
any runtime source inspected by revision and direct hash.

## Immediate experiment

Within 90 wall-clock minutes, use `$kernel-research` to:

1. reconstruct exact per-request, per-layer, prefill, and decode global-KV
   bytes from the bound model configuration and workload;
2. identify the current runtime producer, page-table owner, and first global
   attention consumer that would initiate or await each transfer;
3. implement one deterministic trace simulator and source-level ownership
   sketch for the fixed two-buffer, layer-ahead policy;
4. compare device-resident E5M2 with host-resident E5M2 on identical arrivals,
   including compulsory H2D bytes, buffer memory, event/stream dependencies,
   non-overlappable critical-path time, and complete request/cost bounds; and
5. persist `L40S_GLOBAL_KV_HOST_PREFETCH_OFFLINE_TERMINAL.json` with direct
   hashes, raw layer/step accounting, assumptions labeled by evidence class,
   focused checks, and a real later component command or typed none.

## Decision contract

Pass only if exact semantics and ownership are source-complete, the device
memory saving remains useful after both staging buffers and metadata, and a
conservative overlap bound stays at or below the price-normalized service-time
boundary. Return typed negative if compulsory transfer alone exceeds the
available latency budget or if the runtime cannot preserve exact page
ownership without duplicating the cache.

## Resources and prohibitions

- Spend: `$0`
- Wall clock: 90 minutes
- Researcher profile: `deep`

Do not claim a GPU, use SSH/provider APIs/endpoints, run CUDA, read checkpoint
shards, change KV precision or workload geometry, add compression, offload
local KV, sweep buffer counts or prefetch distances, or count dependent
compute and transfer as fully overlapped.
