# Pinned source cache

`SOURCE_BINDINGS.json` is the durable source identity. The ignored `pinned/`
directory is only a reproducibility cache for official upstream repositories;
it contains no checkpoint or model data.

Populate `pinned/vllm` at
`0164022c907014a27e81c514cd4dff6091904c2b` and `pinned/aiter` at
`6c48c5fa0e7c299adcf1987c8f4817720ceab311`, then apply
`../patches/vllm_aiter_ptpc_bridge.patch` to vLLM with
`git apply --unidiff-zero` before running the CPU screen or target benchmark.
The original and patched SHA-256 identities of every changed or consumed
source file are recorded in `../SOURCE_BINDINGS.json`.
