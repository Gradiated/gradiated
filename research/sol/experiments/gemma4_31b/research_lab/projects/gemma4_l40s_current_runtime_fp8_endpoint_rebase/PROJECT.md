# Gemma 4 current-runtime FP8 L40S endpoint rebase

## Question

Does one current official SGLang revision provide a source-complete
single-L40S path for the exact Gemma 4 dynamic-FP8/E5M2 c32 endpoint, with a
credible complete bound at or below `1.4776251501079425 s/request`, sufficient
to justify the campaign's final bounded provider measurement?

## Why it matters

The locked quality-qualified H200 denominator is
`0.625149101968745 s/request`, and the 20%-lower target is
`0.500119281574996 s/request`. At the shared production-planning rates of
`$3.25/H200-hour` and `$1.10/L40S-hour`, an otherwise scope-matched L40S
endpoint reaches the same price-normalized target at
`1.4776251501079425 s/request`.

The historical L40S online-FP8 result is not a current full-stack endpoint: an
older c12 raw-component calculation bounded linears plus attention/KV at
`2.091299 s/request`. The later QServe/W4 and AWQ realizations failed their
representation or exact-consumer gates. This project changes both the runtime
revision and the measured full-stack consumer while preserving the exact
checkpoint, dynamic-FP8 representation, E5M2 KV cache, hybrid attention,
workload, and product semantics. It must establish a source-supported reason
that the current runtime could overcome the old bound; a generic version
refresh is not enough.

The measured Nebius L40S experiment rate is `$0.8629833/hour`. A hard
40-minute provider lifecycle costs at most `$0.5753222`, inside this project's
requested cumulative `$0.59` authority. The request is not provider authority:
no resource may be created until a later director observes the exact durable
reservation and a positive offline terminal.

## Bound inputs

- Model: `google/gemma-4-31B-it`
- Revision: `b9ea41a2887d8607f594846523f94c6cc75ac8a4`
- Workload: 32 simultaneous requests, 4,214 prompt tokens, 358 completion
  tokens, 535 shared-prefix tokens and 3,679 fresh prompt tokens per request.
- Required representation: dynamic E4M3 FP8 transformer linears, BF16
  embedding/logits where required, E5M2 KV cache, TP1, 50 local-window
  head-dim-256 layers and 10 global head-dim-512 layers.
- Retained serving choices: dynamic chunking with 2,048-token chunks, fused
  Q/K normalization and RoPE, page size one, exact Gemma tool parser, and the
  qualified non-reasoning text path unless the selected current source proves
  a semantically identical replacement.
- Qualified H200 workload terminal:
  `../gemma4_prefill_cuda_graph_padding_rebase/inputs/workload/QUALIFIED_TERMINAL.json`
  at SHA-256
  `7090c0ebb733f5021c464bc55d82fcd68e2abb52b820408c89724d95c03fd9dd`.
- Shared price inventory:
  `../../../../../../factory/data/gpu_prices.json`; require its recorded
  freshness and bind its direct hash.
- Target accelerator: one NVIDIA L40S, SM89, 48 GiB, PCIe Gen4, no peer GPU.

Mechanically extract checkpoint, workload, runtime, launch, and price
identities from their authoritative artifacts. Do not hand-transcribe an
immutable digest into an executable packet.

## Scope

Use `$evidence-research`. Work for at most 90 wall-clock minutes, 3 local
CPU-hours, 3 GiB of new non-checkpoint artifacts, and `$0` in this offline
cycle. Inspect at most two official current SGLang revisions, select exactly
one before implementation, and bind its commit, image or reproducible image
build, and direct source hashes. Do not perform a runtime sweep.

Trace the production path from model configuration and dynamic-FP8 loader
through every Gemma transformer linear, hybrid local/global attention backend,
E5M2 KV producer/consumer, graph or eager execution, logits, sampling, and
tool output. The selected path must support SM89 rather than merely compile
Hopper-only code. Account for checkpoint residency, weights, KV state, graph
buffers, workspace, allocator headroom, and image/checkpoint setup inside one
48-GiB device and the 40-minute lifecycle.

Implement the minimum full-stack consumer and bounded detached owner in this
same project. A positive packet must contain the actual current-runtime launch
and owner code from atomic GPU-pool claim through heartbeat, strict
source/image identity, checkpoint staging, finite coherence/path checks, one
exact c32 invocation, typed retrieval, expected-claimed-at release, and
retained same-claim repair for ordinary pre-science integration defects.
Scientific identities and one c32 submission remain immutable; launcher,
runtime adapter, path, and retrieval code remain narrowly repairable.

Derive a complete candidate-favorable and candidate-adverse service-time
interval from source-supported SM89 work, the historical exact L40S
measurements, mandatory communication, memory movement, setup, failures, and
all-in production rate. Do not transfer H200 throughput, use peak FLOPS as
performance, or claim current-runtime speed from source presence. The offline
gate passes only if the conservative interval still includes
`<=1.4776251501079425 s/request` and every required exact consumer is
reachable.

Return typed `none` if current official SGLang lacks any required Gemma,
dynamic-FP8, E5M2, SM89, graph, parser, or memory-fit boundary; if the old
measured L40S floor cannot be overcome by a source-identified change; if the
complete conservative interval is entirely slower than the economic hurdle;
or if no source-complete one-arm endpoint owner fits 40 provider minutes.

Do not claim a GPU, use SSH or provider APIs, run CUDA or an endpoint, copy or
read checkpoint shards, create a provider resource, build multiple runtime
variants, change workload parameters, switch KV precision, use W4/AWQ/QServe,
or reopen the closed L40S component arms.

## Terminal

Persist `L40S_CURRENT_RUNTIME_FP8_REBASE_OFFLINE_TERMINAL.json` with:

- selected official revision, source URLs, retrieval time, image/build
  identity, and direct hashes;
- mechanically bound model, checkpoint-manifest, workload, launch, price, and
  prior-L40S evidence identities;
- end-to-end producer/consumer and semantic ownership contracts;
- SM89 support, exact tensor geometry, memory fit, graph, KV, logits, parser,
  and failure-path evidence;
- the precise source-level delta that could overcome the old L40S bound;
- complete service-time, completion-latency, memory, setup, reliability, and
  production-cost intervals with evidence labels and uncertainty;
- focused offline checks and direct hashes of the full-stack consumer and
  detached owner; and
- either one exact later director lifecycle/owner command bounded to 40
  provider minutes or typed `none`.

A positive terminal prepares one direct economic falsifier. It does not
authorize provider creation, claim, CUDA, endpoint, quality promotion, or
production deployment.
