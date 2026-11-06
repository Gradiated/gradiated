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
`d9e99b0792a5e93b78ea9bea62a68167e36ddd9e`. Its native compressed-tensors
MXFP4 weights and MXFP8 expert activations are retained. The launcher selects
the `flashinfer_mxfp4` runner with `--flashinfer-mxfp4-moe-precision default`,
which dispatches to the Blackwell TRT-LLM MXFP4 kernel with MXFP8 activations.
The distinct `flashinfer_trtllm` runner does not support this checkpoint's MXFP4
method. The launcher supplies no target dtype or quantization override.
The model's native BF16 attention and control tensors are not a full-model
precision fallback. ReplaySSM uses FP32 recurrent state; this state allocation
does not upcast target weights or expert activations. Native FP8 KV is retained.

The provisional profile reserves eight B300 UUIDs on one host and uses TP8,
85% static device memory, a 0.45 KDA-to-KV memory ratio, an 8K-token prefill budget,
prefill/decode interval zero and decode graphs through batch five. DFLASH uses
block five, non-overlap scheduling and ReplaySSM. Its draft is
`RadixArk/Kimi-K3.1-Dflash2-Preview` at
`d0d8bc2e3c6d0a195d2e00a49017e71ca8d881f1`, with the explicit `cutedsl_mla`
draft attention backend and the checkpoint's default recent window. Its pinned
config and 5,569,631,720-byte weights are bundled at `models/kimi-dflash`.
Build and runtime verification check every file's size and SHA-256 against the
pinned manifest and archive provenance. The draft has no host Hugging Face cache
dependency; archive disk accounting covers it and cache eviction cannot remove it.
Both parsers
are `kimi_k3`; `OMP_NUM_THREADS` and `MAX_JOBS` are eight. Exact rebuilt-archive
GPU and SDK qualification remains required. A DCP8/EP2 comparison is still a
separate candidate; it is not enabled by this provisional launcher.

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
runtime. Its single-worker frontend admits five requests and queues two for
at most sixty seconds, disables retries, and keeps each permit through response
completion. The gateway routes using the same five-request capacity.
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

The entrypoint preserves the host's assigned UUIDs in `NVIDIA_VISIBLE_DEVICES`
and resolves their physical indices with `nvidia-smi` before setting numeric
`CUDA_VISIBLE_DEVICES` in the same assignment order. Missing or duplicate UUIDs
or indices stop startup. This accommodates the pinned custom-all-reduce
implementation's numeric device parser without changing host ownership.
Custom AllReduce V2 is enabled by SGLang's default; `--enable-symm-mem` is a
different allocator policy and is not enabled here. The portable archive also
retains the image's Ninja 1.13.2 executable, whose absence otherwise prevents
the custom collective's first CUDA JIT build.

The configured 1M context requires a resident token pool large enough for the
request and its output. A separate TP8/B5 arm used a 0.45 KDA-to-KV ratio,
sixteen running requests and graph capacity, 2K prefill chunks and prefill/decode
interval four. It passed a native capacity smoke with 1,047,589 rendered input
tokens and 512 generated tokens at 213.06 decode tokens/s, with 97.16 seconds to
first token. A prefix-reuse retrieval smoke found the planted middle-context
marker; the measured pool held 1,079,680 tokens. That arm failed the 32K cold
throughput holdout and is not selected. Its near-limit result does not qualify
the provisional 8K-chunk, interval-zero profile, which still needs long-context
and exact immutable archive qualification. Earlier three-stream throughput
results also used a different 0.9 ratio and batch-32 runtime; they do not qualify
this complete five-request profile. The optimization target is
maximum measured aggregate throughput while the median admitted stream decodes
at least 65 generated tokens/s under the qualified prompt and concurrency mix.
Record TTFT and queueing separately; do not count cached prompt tokens as decode
throughput. Initial tuning and deployment use only the reserved 8xB300 host
`01a0fbf8-06fc-7658-96e1-ae72f7dba135` (RunPod `dv31b4wrd2yc8n`), with one
Kimi replica. The other 8xB300 host, `01a0fbf7-5276-700b-903b-7e04da150ed6`,
continues serving GLM uncensored and is outside Kimi's active placement. Preserve
its processes and configuration, and every other production runtime and replica
count. Expanding Kimi to a second node is a separate deployment change.

The public model starts unavailable and advertises text input only. Its initial
release uses the existing Chat transport and omits `tokenizer_mode`; SGLang owns
prompt rendering, tokenization and usage, so this deployment needs no gateway
tokenizer change. The checkpoint ships a tiktoken vocabulary rather than a
Hugging Face chat template or `tokenizer.json`; a future token-ID transport
would need a qualified native encoder. Image support must be qualified before
expanding the catalog.

Keep `gradiated.com/kimi-k31=reserved:NoSchedule` on the Kimi Node so other
pending models cannot take this reservation. The host inventory declares the
taint for virtual kubelet creation and reconciliation. Kimi's generated
Rollout alone adds the matching explicit toleration. Do not add this taint to
the first eight-GPU host, which continues to serve GLM traffic.

The reserved singleton has no relocation destination under its current placement.
Host reimage admission must fail closed before cordon, surge or drain when no
compatible capacity exists, preserving the serving replica. Before a future
GPU-base image pin can reimage this host, arrange separately authorized,
qualified capacity with a reviewed placement change, or a separately authorized
Kimi-only planned downtime procedure. Do not widen placement onto the GLM host
or bypass fleet availability checks to make maintenance proceed.

After GPU qualification and immutable release publication, preview the placement
with `python3 tools/gpu/stage-kimi-pool.py RELEASE_JSON QUALIFIED_SOURCE_SHA`.
The helper accepts only the second host's committed measured inventory and
preserves every existing model and runtime. Add `--write`, render the GPU
configuration and replica rules, and review the generated Kimi resources before
merging. Promote this model's catalog status to `available` in that deployment
change; the gateway requires it for targeted SDK qualification, while normal
routing remains closed until the worker qualifies the deployment.

The initial pool has one host and uses every GPU on it. Its explicit
`allow_single_replica_unavailable` update policy drains the old Kimi replica
before starting its replacement, so Kimi has a planned availability gap during
an update. Other models retain their existing availability policies. Add a
second qualified replica in a separate deployment change before requiring
continuous Kimi availability across runtime updates.

References: [model](https://huggingface.co/moonshotai/Kimi-K3.1-Pro),
[official SGLang cookbook](https://docs.sglang.io/cookbook/autoregressive/Moonshotai/Kimi-K3.1-Pro),
[license](https://huggingface.co/moonshotai/Kimi-K3.1-Pro/blob/main/LICENSE).
