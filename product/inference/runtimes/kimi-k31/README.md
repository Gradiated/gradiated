# Kimi K3.1 Pro SGLang runtime

`bundles/kimi-k31-pro` packages the official Linux amd64 Kimi image
`lmsysorg/sglang@sha256:4a098ad7414702a2271296ac148854448d10710ec3554ac93b57ef194999305a`.
Its recorded SGLang source is `afcd7d6b487a9cbe73e25941971b4cc107e6f9ae`,
and its CPython is 3.12.16. The archive preserves the image's paired Python and
native kernels, including Kimi FlashMLA, 1024-expert FlashInfer routing and Rust
TreeCore. Six hash-pinned overlay layers update eight source files only at this exact revision;
the proposal-model oracle is verified separately. The installed overlay marker,
archive provenance and launcher agree on fingerprint
`6509efad47e02e681caa9cdb49bb9b9375fb94aa30276fcfa5a082e9bfcdab3e`.
Build verification rejects changed source, patches or lineage. Native extensions
remain paired with their upstream source revision.

The checkpoint is `moonshotai/Kimi-K3.1-Pro` at
`d9e99b0792a5e93b78ea9bea62a68167e36ddd9e` by default, or
`yetalabs/Kimi-K3.1-Pro-abliterated` at
`0911ef0765f49d26dfa25bb0d071f29463f8000b` when `MODEL_ID` is set to
`kimi-k3.1-pro-cyber`. Both checkpoints are native
compressed-tensors MXFP4 with MXFP8 expert activations. The launcher selects
the `flashinfer_mxfp4` runner with `--flashinfer-mxfp4-moe-precision default`,
which dispatches to the Blackwell TRT-LLM MXFP4 kernel with MXFP8 activations.
The distinct `flashinfer_trtllm` runner does not support this checkpoint's MXFP4
method. The launcher supplies no target dtype or quantization override.
The model's native BF16 attention and control tensors are not a full-model
precision fallback. ReplaySSM uses FP32 active recurrent state (`--mamba-ssm-dtype float32`);
this state allocation does not upcast target weights or expert activations. Native FP8 KV is retained.

The default profile (`MODEL_ID` unset or `moonshotai/kimi-k3.1-pro`) retains
its qualified stock configuration: eight B300 UUIDs on one host, TP8, 85% static
device memory, a 0.45 KDA-to-KV memory ratio, an 8K-token prefill budget,
shortest-prefill-first scheduling, prefill/decode interval four while any request
is running, and decode graphs through batch five (`ACTIVE_REQUESTS = 5`). DFLASH
uses block five, non-overlap scheduling and ReplaySSM. Its draft is
`RadixArk/Kimi-K3.1-Dflash2-Preview` at
`d0d8bc2e3c6d0a195d2e00a49017e71ca8d881f1`, with the explicit `cutedsl_mla`
draft attention backend and the checkpoint's default recent window. Its pinned
config and 5,569,631,720-byte weights are bundled at `models/kimi-dflash`.
Build and runtime verification check every file's size and SHA-256 against the
pinned manifest and archive provenance. The draft has no host Hugging Face cache
dependency; archive disk accounting covers it and cache eviction cannot remove it.
Both parsers are `kimi_k3`; `OMP_NUM_THREADS` and `MAX_JOBS` are eight.

When `MODEL_ID=kimi-k3.1-pro-cyber`, the launcher selects the
Nebius 8xB300-qualified 16-slot profile (`CYBER_ACTIVE_REQUESTS = 16`):
TP8 + EP8 + DCP8, 88% static device memory, a 1.5 KDA-to-KV memory ratio with
INT8 Mamba radix checkpoints (`--enable-int8-mamba-checkpoint`; active decode
state stays FP32; 297 active FP32 Mamba slots, 594 cached INT8 Mamba checkpoints,
6.46M FP8 KV tokens, ~17 GB/GPU free HBM headroom after CUDA graphs), a 16K-token
prefill chunk budget (`--chunked-prefill-size 16384 --max-prefill-tokens 16384`),
FP8 draft KV (`--speculative-draft-kv-cache-dtype fp8_e4m3`), and decode graphs
and SMG admission through batch 16 (`--queue-size 0`), while retaining DFLASH
block five, non-overlap scheduling (preserving `seed`, `frequency_penalty`, and
`presence_penalty`), ReplaySSM, shortest-prefill-first, and interval four.

On a Nebius 8xB300 spot benchmark (`yetalabs/Kimi-K3.1-Pro-abliterated`, 16 arms,
archived at `s3://gradiated-dev-training-873716897517/kimi-k31-abliterated/opt-20261125/`),
this 16-slot abliterated profile held 88.0% prefix cache hits across 32 concurrent
2K-48K sessions (vs 67-76% eviction collapse without DCP8/INT8 checkpoints),
delivered 62.2-62.5 p50 TPS (~791-795 agg TPS, 1.12s p50 / 1.98s p95 TTFT) at all
16 slots full on realistic 88%-cached multi-turn traffic (62.1 p50 / 885.5 agg /
0.80s p95 TTFT warm; 464-474 agg cold = 96-98% of the 485 TPS no-spec cold ceiling),
kept 128K prefill TTFT at 8.1s with 1.06s short-probe TTFT and 42.6 TPS
running-stream decode under mixed load, and passed all six production qualification
smoke checks (non-stream/stream `READY`, `/v1/messages/count_tokens`, `dcp=8`
512-token quantum cached prefill warmup, `seed` + penalties, and tool calling).
The stock 5-slot admission and qualification table below applies to the default
`moonshotai/kimi-k3.1-pro` profile.

The source overlays correct committed-history and candidate-prefix penalties,
add per-request sampling seeds, guard seeded admission and clamp Kimi's cached
usage to its reported prompt count in bodies and headers. Seeded admission
requires TP8, PP1, B5/B8, non-overlap and sequential verification with an available
verifier and no NVIDIA megakernel. Seeds control sampling randomness on a
best-effort basis; model numerical differences across batching can change output.
This profile does not promise batch-invariant token sequences or enable global
deterministic inference. Unsupported sampling settings fail rather than silently
changing semantics.

The CUDA seed path fuses each counter-based Philox draw into one Triton kernel.
It preserves the reference's 24-bit float32 lattice, seed/absolute-position/stream
keys and unseeded sentinel rows; the portable Torch reference remains available.
Startup exercises every batch size from one through the active limit, with
seeded, mixed and inverse-mixed rows, before publishing readiness. This warms
shape-specific kernels before batches shrink or grow during serving.

SMG 1.13.0 supplies the same guarded refused-upload drain fix used by the GLM
runtime. Its single-worker frontend admits five requests and queues none: a
sixth request gets an immediate `429 admission_queue_full`. The gateway retries
it on the other replica and, if that is full too, returns the capacity error so
the caller can go elsewhere at once. It disables retries
and keeps each permit through response completion. The backend runs with
`SGLANG_MAX_NEW_TOKENS_LIMIT=131072`, because the gateway sends no output limit
when a caller sets none. The gateway routes using the same five-request capacity.
Changing that capacity changes the immutable runtime and requires matched
measurements and requalification.

Five requests is an operator choice that trades per-stream decode speed for
aggregate throughput. Decode rate is tokens after the first, over time after the
first token. Four requests is the largest limit at which the median stream stayed
at or above 80 for both default sampling and seeded requests with
frequency/presence penalties; five adds about 7% aggregate throughput over four
with medians of 76-78 (default) and 67-80 (seed+penalty). These are
fresh-prefix 2K/8K/32K prompts with 512 output tokens, two trials per cell, on
the fused-Philox source:

| Limit | Default median TPS | Seed+penalty median TPS | Slowest stream | Aggregate TPS |
| ----- | ------------------ | ----------------------- | -------------- | ------------- |
| 2     | 159-174            | 129-147                 | 89             | 200-232       |
| 3     | 129-142            | 92-112                  | 68-74          | 245-281       |
| 4     | 97-110             | 80-89                   | 59-64          | 278-309       |
| 5     | 76-78              | 67-80                   | 47-61          | 298-331       |
| 6     | 82-83              | 62-66                   | 44-47          | 322-353       |
| 8     | 62-74              | 57-58                   | 36-39          | 342-374       |

At five requests, the slowest streams fall to about 47-61 TPS while other
requests' long prefills share the step. Penalties also lower DFLASH acceptance,
because the draft proposes without them. Time to first token across the mix
stays close to four requests: median about 1.3 seconds, p90 about 2.4 seconds and
worst 3.6 seconds, before any frontend queueing. Six requests pushed the p90 to
about 5.2 seconds. Archive qualification at five requests must pass both the
default-sampling and the seed+penalty probe runs with `--floor-tps 65` on the
median stream.

The host supplies `NVIDIA_VISIBLE_DEVICES`, `RUNTIME_PORT`, `WARMUP_PORT` and
`GRADIATED_RUNTIME_ROOT`. The frontend uses `RUNTIME_PORT`, the native backend
uses `RUNTIME_PORT + 4`, and SMG metrics use `RUNTIME_PORT + 5`. These listeners
bind only loopback. Warmup health remains closed until real streaming requests
exercise cold prompt shapes, concurrency and mixed prefill/decode. The product
worker must independently qualify this exact runtime incarnation through the
production SDK before normal routing.

After startup, readiness requires both SMG `/readiness` and the native backend's
`/health_generate`, each with a two-second HTTP timeout. The native check requires
a scheduler response even when generation is disabled on `/health`; a live HTTP
process cannot keep a stalled GPU engine ready. While busy, SGLang can acknowledge
health through normal scheduler progress; while idle, it generates one token.
Failed checks make the allocation unready so new eligible requests use other
capacity, including OpenRouter, without shortening legitimate prefill deadlines.

The entrypoint preserves the host's assigned UUIDs in `NVIDIA_VISIBLE_DEVICES`
and resolves their physical indices with `nvidia-smi` before setting numeric
`CUDA_VISIBLE_DEVICES` in the same assignment order. Missing or duplicate UUIDs
or indices stop startup. This accommodates the pinned custom-all-reduce
implementation's numeric device parser without changing host ownership.
Custom AllReduce V2 is enabled by SGLang's default; `--enable-symm-mem` is a
different allocator policy and is not enabled here. The portable archive also
retains the image's Ninja 1.13.2 executable, whose absence otherwise prevents
the custom collective's first CUDA JIT build.

With the default policy and interval zero, a long uncached prompt ran its 8K
chunks back to back: every running stream stopped and a newly admitted short
prompt waited for the whole prefill. On a spot 8xB300 running the
`kimi-k31-19bbe4a04aaa` archive, three streams and a probe slot, a 384K-token
prompt froze running streams for 22 s and gave the short probe a 21 s TTFT.
Shortest-prefill-first reserves chunk budget for shorter waiting prompts (probe
TTFT 0.44 s at 384K and 0.87 s at 128K); interval four gives running streams
four decode rounds after each chunk (about 22 tokens/s during the prefill on
essay text, instead of about 1). The long prompt's TTFT rises from 21.8 to 25.6
s. Five-stream closed-loop throughput matched the old profile (median 65-96
against 75-90 tokens/s per stream across two trials each; aggregate 347-463
against 339-448). Mixed chunked prefill added little on top (running streams
fall back to one plain token per mixed step) and interval two left streams at
12-17 tokens/s, so neither is selected. Longer intervals trade more long-prompt
TTFT for stream speed: with random-token streams, interval 16 roughly doubled
stream speed over interval four but raised the 384K TTFT to 36 s.

The configured 1M context requires a resident token pool large enough for the
request and its output. A separate TP8/B5 arm used a 0.45 KDA-to-KV ratio,
sixteen running requests and graph capacity, 2K prefill chunks and prefill/decode
interval four. It passed a native capacity smoke with 1,047,589 rendered input
tokens and 512 generated tokens at 213.06 decode tokens/s, with 97.16 seconds to
first token. A prefix-reuse retrieval smoke found the planted middle-context
marker; the measured pool held 1,079,680 tokens. That arm failed the 32K cold
throughput holdout and is not selected. Its near-limit result does not qualify
the provisional 8K-chunk, interval-four profile, which still needs long-context
and exact immutable archive qualification. Earlier three-stream throughput
results also used a different 0.9 ratio and batch-32 runtime; they do not qualify
this complete five-request profile. The optimization target is
maximum measured aggregate throughput while the median admitted stream decodes
at least 65 generated tokens/s under the qualified prompt and concurrency mix.
Record TTFT and queueing separately; do not count cached prompt tokens as decode
throughput. Tuning used the then-reserved 8xB300 host
`01a0fbf8-06fc-7658-96e1-ae72f7dba135` (RunPod `dv31b4wrd2yc8n`). The pool now
runs one replica on `01a0fbf7-5276-700b-903b-7e04da150ed6`, the only host retaining
the `kimi-k31` reservation. Host `01a0fbf8` returns to shared capacity for
DeepSeek replicas and other unreserved pools. DeepSeek has no required same-host
affinity. Changing host reservations does not stop or replace provider instances;
the taint blocks new pods and does not evict running ones.

The public model is available and advertises text input only. Its exact
OpenRouter mapping is `moonshotai/kimi-k3.1-pro`. The gateway prefers qualified
local deployments and uses OpenRouter when local capacity is absent, saturated
or fails before output, subject to the [external-capacity rules](../../../services/gateway/ARCHITECTURE.md#external-capacity-openrouter).
Requests originating from OpenRouter, deployment-pinned requests, and requests
with unsupported external parameters stay local. Fallback requires zero retention,
no data collection and support for every forwarded parameter. Its fixed provider
ceilings are $2 input and $10 output per million tokens, the separate endpoint
medians observed on 2026-11-13, independent of service tier. These ceilings do not
change customer billing: standard prices are $0.25 per million input tokens,
$0.025 cached input and $2.50 output/internal reasoning. There is no separate
cache-write price: the gateway adds a cache-write price on top of input, so
cache writes are charged at the input rate. Its initial
release uses the existing Chat transport and omits `tokenizer_mode`; SGLang owns
prompt rendering, tokenization and usage. For the public Anthropic token-count
endpoint, the gateway forwards the original counting request to a healthy Kimi
deployment's `/v1/messages/count_tokens`, with a ten-second deadline and no
generation admission or billing. The checkpoint ships a tiktoken vocabulary
rather than a Hugging Face chat template or `tokenizer.json`; a future token-ID transport
would need a qualified native encoder. Image support must be qualified before
expanding the catalog.

Both Kimi hosts carry the `gradiated.com/reserved=kimi-k31:NoSchedule`
reservation, so other pending models cannot take them. The host inventory
declares the taint for virtual kubelet creation and reconciliation. Kimi's pool
names the `kimi-k31` reservation, so its generated Rollout alone tolerates the
taint and is confined to the reserved hosts.

Both Kimi hosts are full: each runs one replica on all eight GPUs, and no other
eligible 8xB300 host exists. The fleet rollout checks relocation capacity
before cordoning a host for re-image, so it blocks on either Kimi host and
re-images neither. Both replicas keep serving, but a GPU-base pin cannot reach
these hosts on its own. Re-imaging one needs separately arranged, qualified spare
capacity or an authorized Kimi planned-downtime procedure. Do not bypass fleet
availability checks to make maintenance proceed. Kimi's weights are staged by
hand in `/var/lib/kimi-k31` (checkpoint, draft and an `hf` cache of snapshot
symlinks owned by `runtime`), not in the host-managed Hugging Face cache, because
the 1.5 TB checkpoint does not fit the host agent's cache eviction budget beside
a second copy. A re-imaged host loses that directory, so the weights must be
staged again before its replica can start.

After GPU qualification and immutable release publication, preview the placement
with `gradctl gpu stage-kimi-pool RELEASE_JSON QUALIFIED_SOURCE_SHA`.
The helper requires exactly two hosts carrying the reservation, each with
committed 8xB300 inventory, and preserves every existing model and runtime. It
keeps both replicas warm with ten `min_slots`. Add `--write`, render the GPU
configuration, and review the generated Kimi resources before merging. The
catalog status is already `available`; normal routing to the Kimi
deployments stays closed until the worker qualifies them. With OpenRouter
capacity disabled, Kimi cannot serve requests until local qualification succeeds.

The pool has two replicas, one per host, each using every GPU on its host
(ten `min_slots` at five slots each, and `max_replicas` two). An update replaces one replica at a
time: the PodDisruptionBudget keeps one available, and the surge pod waits until
the old replica frees its host. Kimi capacity halves during an update rather than
dropping to zero.

References: [model](https://huggingface.co/moonshotai/Kimi-K3.1-Pro),
[official SGLang cookbook](https://docs.sglang.io/cookbook/autoregressive/Moonshotai/Kimi-K3.1-Pro),
[license](https://huggingface.co/moonshotai/Kimi-K3.1-Pro/blob/main/LICENSE).
