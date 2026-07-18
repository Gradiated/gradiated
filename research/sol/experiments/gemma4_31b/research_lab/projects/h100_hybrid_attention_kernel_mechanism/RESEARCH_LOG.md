# Research log

## 2026-07-17 — director admission

Activated as the independent deep lane while the L40S direct-FP8 owner executes. It must replace the prior generic fused-attention label with a source/chip causal chain and one exact-shape falsifier or close the branch.

## 2026-07-17 — pinned paged-KV mechanism terminal

- **Question:** can a source-level H100 hybrid-attention change clear 5% of the 1.8249 request/s planning service time without inventing a fused boundary?
- **Action:** traced `gemma4.py` through `Attention`, SM90 backend selection, paged FlashAttention, and Triton unified attention at pinned vLLM revision `ab0a20d...`; ran the deterministic exact-geometry byte/roofline simulation in `derive_mechanism.py`. No GPU, provider, checkpoint, image pull, or compilation was used.
- **Evidence:** local K+V is 16,384 BF16 bytes/token/layer (16 heads x 256 x K/V x 2 bytes), while global K+V is 8,192. Exact decode reads are therefore 429.133 GB/request, 1.538x the earlier constant-8,192-byte floor. FP8 E4M3 halves this to 214.566 GB. At the H100 SXM 3.35 TB/s vendor peak, the reduction is 64.050 ms/request; even granting BF16 the full 50 MiB L2 on every decode step and FP8 none leaves 58.447 ms, 10.67% of the 547.975 ms planning service time versus the 27.399 ms hurdle.
- **Interpretation:** FP8 paged KV is a plausible >=5% HBM mechanism, not a throughput result. Exact arithmetic intensity is 3.80 BF16 FLOP/byte versus the 295.37 FLOP/byte H100 roofline balance. Cross-layer five-local/one-global fusion is source-falsified because o-projection, residual/norm, and MLP dependencies separate the six layer calls; K=V one-copy caching is also invalid after distinct K norm+RoPE and V norm.
- **Next move:** if later admitted, execute only the content-bound BF16-vs-FP8 actual paged producer/consumer contract in `MECHANISM.json`; require the output oracle, >=40% measured DRAM-byte reduction, >=10% component gain, and >=27.399 ms architecture-weighted request saving. Bind an immutable image to the pinned source first because the cached image reports a different vLLM build.
