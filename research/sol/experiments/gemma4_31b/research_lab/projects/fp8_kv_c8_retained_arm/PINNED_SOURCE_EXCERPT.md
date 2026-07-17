# Pinned vLLM FP8-KV scale binding

Source revision: `ab0a20d15129b322f911db578b50c6b35b3167e7`.

The pinned `CacheConfig` accepts `fp8_e4m3`/`fp8` and separately accepts
`fp8_per_token_head`. The scalar path uses checkpoint K/V scales when present;
with `calculate_kv_scales=false` it otherwise defaults to `1.0`. The model
config and weight index for the exact Gemma 4 revision contain no K/V scale
tensors.

The pinned `KVQuantMode` maps `fp8_per_token_head` to
`FP8_PER_TOKEN_HEAD`. The pinned Triton backend stores one FP8 byte per K/V
value and an inline four-byte FP32 scale for each K/V token-head. The cache
writer computes those scales at runtime; the backend reinterprets the bytes
using the current platform FP8 dtype. On Ada this is the native E4M3 FP8
path.

Relevant pinned file hashes:

- `vllm/config/cache.py`: `ee2c0db3e4e6c9e9cab33d8be566c4b8101159d36c0d3787c30d47931ee2a9a4`
- `vllm/model_executor/models/gemma4.py`: `3d63af0ad265d56e09e3244a08102767efb6579a553db2c8213aa8912660b093`
- `vllm/model_executor/layers/attention/attention.py`: `25d708c4075e87ae7af8e8855dd8f5652ff0fdef2f11ec794ec7a7e12d25c2e7`
- `vllm/v1/kv_cache_interface.py`: fetched at the same revision; `fp8_per_token_head` maps to `FP8_PER_TOKEN_HEAD`.
- `vllm/v1/attention/backends/triton_attn.py`: fetched at the same revision; inline scale layout and dynamic scale writer are the execution path.

The generic `--kv-cache-dtype fp8` / `fp8_e4m3` launch is not used: its
checkpoint-scale fallback is ambiguous for this unquantized Gemma checkpoint,
and current first-party Gemma 4 reports associate that path with corrupt
outputs. This packet therefore binds the explicit per-token-head path.
