# GLM Flash SGLang runtime

`bundles/glm-5-3-flash-sglang` packages SGLang source
`f171859219b54e1dad45dda60028034490836974`, CPython 3.12.13, and the
hash-locked Linux x86_64 dependencies. It serves
`dealignai/GLM-5.3-Flash-UNCENSORED-NVFP4` at revision
`745aac2ff0f10acf961f396df3f9418598aa7327` using two B300 GPUs by default.
The profile uses TP2/PCP2 with interleaved context parallelism, Marlin W4A16
experts, two MTP draft steps, FP8 KV, a 16,384-token prefill budget,
shortest-prefill-first scheduling, and 64 decode rounds between prefill steps.
Prefill CUDA graphs are disabled; decode graphs remain enabled. Actual resolved
pool geometry must be recorded during GPU qualification.

## B300 hierarchical prefix cache

The `b300-pcp2` profile serving the uncensored model (`'hicache': True` on both
in `config.py`; delete either to turn the feature off; LoRA serving never uses
it) keeps evicted prefix KV and recurrent state in three tiers:

- GPU: the native KV and Mamba pools.
- Host RAM: `--hicache-size 48` pins 48 GB per rank, split between KV and
  Mamba state, inside the 400 GiB per-replica memory limit (each rank also uses
  ~25 GiB RSS; the rest is weight page cache). The host KV pool is smaller than
  the device pool, so SGLang warns that L2 is less effective; the tmpfs file
  tier is the capacity tier.
- tmpfs (never disk): SGLang's `file` backend in `/dev/shm`, written through
  from host RAM. Each rank evicts its own files LRU at 50 GB (`max_size`) and
  stops writing when less than 30 GB of `/dev/shm` is free (`min_free_space`).
  The pages count against the replica's 400 GiB memory limit.

Request-derived pages may not reach disk (data-retention policy: prompts for
trace-off requests are processed in memory only), so the file tier lives in
tmpfs: `/dev/shm/gradiated-hicache/<runtime directory>/<identity>/<GPU UUIDs>/`.
GPU hosts have no swap. tmpfs pages are charged to the replica's 400 GiB limit,
so each rank keeps at most 50G and writes stop below 30G free in `/dev/shm`.
`<identity>` is the SHA-256 of the qualification identity (bundle digest and
profile settings without ports or root), because stored pages do not record
their dtype or layout. The GPU UUID pair keeps two replicas on one host apart.
A process restart or replacement pod on the same GPUs, bundle and settings
reuses the directory, so the tier survives restarts and rollouts; a host restart
or re-image clears it. At startup the service holds a shared lock on
`<leaf>.lock` and deletes other unlocked leaves idle for an hour. Without
a bundle digest the runtime keeps only the GPU and host tiers. The default
`rank-suffix` key scheme is used because `unified` rejects speculative
decoding. Native `sglang:*` HiCache series are exported unchanged through the
warmup `/metrics` endpoint. This configuration must pass a live B300 test before
a bundle carrying it is pinned.

A prefix is reusable from host or disk only if a node at or below its end
holds a recurrent state there. After prefill, SGLang already places the state
at the last checkpoint-aligned prompt position on a tree node; on that node
and on the request-end node, a guarded overlay of `unified_radix_cache.py`
copies the state to host after any in-flight KV copy of the node acknowledges,
then writes the node to disk. Otherwise a KV copy queued before the state was
attached can leave host and disk with KV but no state. The overlay is on
whenever HiCache is (SGLang starts with `GRADIATED_MAMBA_PROMPT_END_CHECKPOINT=1`),
since HiCache serves no host or disk hit without it; it is forced off otherwise. The same overlays carry upstream
[#48421](https://github.com/sgl-project/sglang/pull/48421) (no partial disk
prefetch for hybrid models) and
[#47680](https://github.com/sgl-project/sglang/pull/47680) (skip a mid-request
state donation instead of crashing when every state slot is locked). Upstream
lets only TP rank 0 of an MLA model write disk pages, but under attention CP
each CP rank keys its own slice of every page, so with TP2/CP2 rank 1's slice
was never written and every disk lookup missed; an overlay of
`hicache_storage.py` makes the first TP rank of each CP group a writer. The
bundle builds SGLang's HiCache page-hash extension with OpenSSL headers at
build time; on AVX2 hosts SGLang loads that build instead of compiling one.

## H200 TP2 profile

The same archive also carries `GLM_SGLANG_PROFILE=h200-tp2`. The default
`b300-pcp2` profile retains the B300 launch settings above. The service checks
both assigned GPU names before starting the backend and refuses a mismatched
profile. H200 enrollment and placement retain the `H200` product identity;
GH200 is not accepted as H200.

H200 uses TP2 without prefill context parallelism, Marlin W4A16 experts,
FP8 E4M3 KV, `flashmla_sparse_q8` DSA prefill and TileLang decode. It does not
use Blackwell's `trtllm` sparse attention. GLM's four-token pooled index uses
a logical page size of 256, giving FlashMLA its required 64 physical slots.

H200 retains MTP using three draft steps and four verification tokens. The
previous two-step/three-token FP8 configuration produced repetitive incorrect
output under CUDA graph replay. Disabling graph padding avoided the short-case
corruption but fell back to slow eager execution for unsupported batch sizes.
Four verification tokens satisfy TP2 graph alignment for batch sizes one through
four, avoiding the failing padded path without disabling graphs or speculation.
This is a qualified launch configuration, not a repair of the upstream replay bug.

GLM prefix reuse needs both full-attention KV and recurrent-state checkpoints.
The H200 profile uses a recurrent-to-full-cache memory budget ratio of 1.8;
leaving the default at 0.9 reduced recurrent slots and destroyed cache reuse in
the deeper-MTP benchmark. At 0.85 static memory, the balanced FP8/MTP candidate
allocated 1,419,776 KV tokens and 77 recurrent slots versus 842,496 tokens and
63 slots for BF16/MTP. It passed 25 synthetic correctness checks including
14K-token cached prefixes and four concurrent requests. In the final two warm
synthetic trials (~46K input/512 output, concurrency four), it delivered
238–243 aggregate output tokens/s and 123–125 per-request decode tokens/s;
the BF16 control's final warm trial delivered 254 and 128, respectively.
These are one-host, ordered synthetic comparisons, not production capacity
or general numerical-quality qualification. The 0.90 launch setting below must
also pass the same checks and observed-memory verification before promotion.

Six input/output-hash-guarded overlays adapt upstream
[SGLang PR #44217](https://github.com/sgl-project/sglang/pull/44217) at
`6b1ac36a9bf8cd1958f17c9937c85d86cbdc1c91` to the pinned source. They let
Q8 prefill and TileLang decode share raw 512-dimensional NoPE FP8 KV rows,
including KPool live-tail indices. They do not use the incompatible packed,
scaled FlashMLA KV layout. The original quantization and mHC overlays remain.
B200/B300 retain their existing attention backends and MTP settings.

The H200 limits are three active requests, two queued requests, a
4,096-token prefill budget, 90% static device memory, and decode graphs through
batch three. SMG, SGLang, warmup admission and exported capacity metrics use the
same three-request limit. The runtime's `runtimes.json` entry declares the same
`active_requests` for gateway routing weights; `tools/gpu/render-config.py`
rejects an entry whose value differs from its launcher profile. The host profile requests and limits 32 CPU and
320 GiB of system RAM, fitting the first pod's provider-reported 377 GB before
enrollment measures its cgroup allowance. Each replica reserves both H200s.
The 1M context setting remains a configured bound, not measured evidence of
1M-token residency or latency. Record actual KV/recurrent pool capacity and
qualify the longest supported requests on H200 before production promotion.

CPU build checks and the synthetic GPU smoke do not qualify general numerical
quality, long-context capacity or production throughput. The actual packaged
runtime must pass deployment qualification before promotion. See
[H200 deployment preparation](../../../../docs/INSTANCE_SETUP_PLAN.md#h200-tp2-alongside-b300)
for enrollment, staging, qualification, promotion and rollback.

## B200 PCP2 profile

The `b200-pcp2` profile serves the same checkpoint on two B200 GPUs and is
selected from the assigned GPU names, like the other profiles.
B200 (SM100) and B300 (SM103) share the Blackwell kernels; the pinned SGLang
selects `trtllm` DSA for any compute capability 10 or later. The profile keeps
every B300 launch setting except the admission limit: six active requests,
with decode graphs through batch six, because each B200 has about two thirds
of a B300's HBM. Hardware validation refuses B300 and GB200 GPUs for this
profile and B200 GPUs for the B300 profile. No B200 startup, capacity or
throughput result is claimed here; qualify it as described for H200.

Three compatibility patches preserve the measured configuration: gate/up global-scale
folding before Marlin conversion, the corresponding ModelOpt dispatch, and the
GLM NextN quantization guard. Their input and output SHA-256 digests are checked
at build time. A fourth guarded patch warms GLM mHC prenorm kernels over the
native token-count buckets during weight loading, before KV-pool sizing and
readiness. It uses the loaded GLM boundary and real normalization weights, runs
once for the target and MTP decoder, and synchronizes TP ranks after releasing
startup tensors. This moves the known mHC shape compilations into startup instead of
leaving them on the active decode path. GPU qualification of each built artifact is still
required. The downstream Marlin scale representation is lossy; the compatibility patches
and the shared checkpoint do not establish bit-exact equivalence to another
runtime. The package does not select the experimental W4A4 backend.

## Admission and ports

SMG 1.13.0 owns the loopback frontend. Its Python wheel is rebuilt from pinned
source `91b3e0c440f9ab7971aa3ba48b049d951bd963de` with a guarded HTTP upload
rejection fix. A refused request drains its body within the configured request
timeout (900 seconds for this runtime) before returning the native error, so
supported slow uploads do not become early-close broken-pipe 502s in NGINX. Expired queue slots are released before that drain.
The compiled extension exports a build marker checked in the actual archive.
The patch adds no scheduler or admission queue. A single backend URL, disabled
router retries, 12 active permits, two queued requests, a 10-second queue timeout,
and disabled token-bucket rate limiting bound admission. A permit lasts through
the response body. Queue-full responses are HTTP 429; queue expiry returns
HTTP 503. Requests already holding a permit may still wait inside SGLang for
scheduling or KV capacity; the frontend queue timeout does not bound that wait.
The gateway retains responsibility for failover between replicas.

The SGLang backend has 12 running slots and no separate native queue cap.
Its native queue limit is applied during intake before scheduling: a cap of two
can reject an idle burst after its first two requests, despite available running
slots. The official frontend avoids that intake failure while bounding total
requests sent to the backend.

The host assigns `NVIDIA_VISIBLE_DEVICES`, `RUNTIME_PORT`, `WARMUP_PORT`, and
`GRADIATED_RUNTIME_ROOT`. Exactly two distinct GPU UUIDs and TP2 are required.
Ports remain within the host's eight-port allocation:

| Offset from `RUNTIME_PORT` | Service                                            |
| -------------------------- | -------------------------------------------------- |
| 0                          | SMG inference frontend                             |
| 1                          | Existing Desmond control service                   |
| 2                          | Reserved adapter service; adapters are unsupported |
| 3                          | Qualification health and aggregated metrics        |
| 4                          | Private SGLang backend                             |
| 5                          | Native SMG Prometheus listener                     |

Every listener binds to `127.0.0.1`. `MAX_QUEUED_REQUESTS` and
`MAX_QUEUED_TOKENS` are vLLM settings and are rejected by this profile.
No custom admission queue or scheduler is installed.

## Startup, metrics, and drain

The service starts SGLang, waits for its health and exact served-model identity,
then starts SMG. Its native `/readiness` endpoint must confirm a healthy
registered worker; `/health` is only router process liveness. The shared GLM supervisor qualifies cold prompt shapes, mixed
requests, and concurrency up to the profile's active plus queued limit using the real OpenAI endpoint. Readiness
stays closed until those checks pass and closes before termination signals are
forwarded. A component exit shuts down the other component. The runtime launcher
and host agent retain their existing process-tree and cgroup cleanup guards.
The host proxy drains accepted HTTP streams before terminating the bundle.

Qualification runs in one of three modes, logged as `{"qualification": ...}` and
exported as `gradiated_runtime_startup_qualification{mode="..."} 1`:

- `full`: cold groups at 180 s, then the mixed-prompt groups and any cold
  concurrency or mixed-prefill group that took longer than 25 s, at 25 s. A
  passing full run writes a record under
  `$XDG_CACHE_HOME/glm-sglang/qualification/`, keyed by the bundle digest, the
  hardware profile settings, the assigned GPU UUIDs, names and driver, the
  shapes and the queue limits.
- `short`: a record younger than seven days matches, so only the 25 s groups run.
- `short_to_full`: the short pass failed or a group was more than twice its
  recorded latency plus 1 s slower, so the full qualification ran and rewrote the
  record.

Without a bundle digest or readable GPU inventory, every start runs `full` and
writes no record. Shutdown or the startup deadline during a short pass still ends
startup.

Desmond uses the warmup port for `/health` and `/metrics`. The metrics response
retains native `sglang:*` and `smg_*` series, avoiding duplicate Python process
series. It also exposes explicit frontend active, waiting, and queue-age limits.
The compatibility series `vllm:kv_cache_usage_perc` is the maximum valid native
`sglang:full_token_usage` sample: non-evictable full-attention KV usage divided by
pool capacity. It excludes evictable cache entries. Missing, malformed, or
out-of-range samples make metrics unavailable rather than report zero.
SGLang's overall `token_usage` includes recurrent-state pressure; that native
series and the separate Mamba metrics remain available without being relabeled
as KV usage. The allocation's public `/metrics` path does not aggregate SMG;
use the private Desmond/warmup metrics endpoint.

## Portable artifacts and verification

The archive contains pinned packages and source, not the experimental virtual
environment, checkpoints, prompts, credentials, or GPU JIT caches. Build-time
fetches verify all 37 public NVIDIA TRTLLM FMHA/BMM/GEMM checksum manifests and
headers against the pinned FlashInfer 0.7.2 hashes. Startup verifies and atomically
seeds these files into a writable versioned cubin directory before GPU ranks
start. This avoids concurrent downloads of large headers on a fresh pod.

The bundle also carries FlashInfer autotune results for the B300 profile in
`autotune/`, tuned on a production host. A host's first start otherwise spends
5-11 minutes tuning; the tactics are the same on every B300 host because the
cache key covers only model and parallel settings and the file's metadata covers
library versions and the GPU. `autotune-seed.py` fills a tuning directory only
when no rank has a file there, never blocks startup, and leaves a host's own
results in place. FlashInfer ignores a seed whose metadata disagrees with the
running libraries, so a stale seed costs only the tuning it would have saved.
`test_autotune_seed.py` fails when the pinned FlashInfer or CUTLASS DSL version
changes: refresh the seeds from
`$XDG_CACHE_HOME/glm-sglang/sglang/flashinfer/autotune/` on a host running the
new bundle, or delete them.
Individual cubins remain subject to FlashInfer's native checksum-verified
on-demand downloads; the bundle is not an offline-complete cubin distribution.
Qualify a cold writable cache on B300 hardware, including long-context and mixed
shapes, before promotion. The cache path can be shared across allocations using
the same pinned runtime and must remain writable by the runtime user.

The Docker verification stage extracts the actual archive, imports its pinned
binaries, checks source patch digests, compiles Python sources, parses both native
CLIs, and verifies seeded artifacts through FlashInfer's loader with downloads
disabled. CPU tests exercise native scheduler queue semantics, the compiled SMG
frontend with held SSE bodies, queue expiry, metrics, and lifecycle behavior.
Run local source checks with the pinned SGLang package installed or set
`SGLANG_TEST_SOURCE` to that source tree:

```sh
python3 -m unittest discover -s product/inference/runtimes/glm-sglang -p 'test_*.py'
```

CPU verification does not qualify GPU kernels or gateway behavior. The packaged
runtime still requires cold-cache GPU startup, actual local-gateway tests for
streaming, tools, overload, failover and cancellation, and the authorized canary
before a slow production rollout. Publishing the artifact alone does not change
production selection; roll back to the previous SGLang runtime in the catalogue.
