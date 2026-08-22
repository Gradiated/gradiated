# Gradiated native inference engine

This directory owns the native C++/CUDA inference path. The first target is the pinned
`google/gemma-4-31B-it` release on one NVIDIA H200. The public runtime contract will remain
OpenAI-compatible so the gateway and Desmond do not depend on the execution backend.

The engine is split into independently testable layers:

- `gradiated_engine_model`: strict JSON, Gemma 4 configuration, sharded safetensors metadata,
  tensor-shape and parameter-count validation. It builds without CUDA and never maps all 62 GB
  just to inspect a release.
- `gradiated_engine_cuda`: H200 (`sm_90`) BF16 kernels and CUDA/cuBLASLt execution primitives.
- `gradiated-engine-inspect`: release validation and memory-planning CLI.

The CUDA build pins NVIDIA's header-only cuDNN frontend to commit
`b372d39879d44c91a8d5b342022e74802b6a8da2` (v1.17.0) and links the cuDNN 9 graph runtime from the
node image. This makes the fused sliding-prefill graph reproducible while leaving engine-owned
scheduling, cache layout, global D=512 attention, decode, and sampling in this tree.

The execution roadmap is weight loading, parity-tested single-request forward, hybrid paged KV
cache, continuous batching and prefix reuse, then overlapped frozen-KV speculative decoding. Each
optimization is retained only when it improves sustained cheapest-price compute recovery while
meeting TTFT, TPOT and output-parity gates on the held-out agentic trace workload.

`tools/generate_layer_fixture.py` creates deterministic BF16 reference fixtures for one pinned
decoder layer without loading the full model. Fixture binaries are runtime artifacts; their
manifest and hashes establish exactly which model, layer, seed and shape a CUDA parity run used.
