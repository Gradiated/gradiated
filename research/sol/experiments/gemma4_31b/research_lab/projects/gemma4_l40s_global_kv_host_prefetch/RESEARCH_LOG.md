# Research log

## 2026-07-27T06:27Z — fixed global-KV host prefetch closed on PCIe work

- Question: can ten exact global E5M2 layers remain pinned-host canonical and
  use one deterministic two-buffer, one-global-layer-ahead policy without
  pushing exact c32 above `1.4776251501079425 s/request`?
- Action: direct-hashed SGLang commit `c6a6200a1a77...`; traced
  `Gemma4Attention` production through `SWAKVPool.full_kv_pool`,
  `ReqToTokenPool`, `SWATokenToKVPoolAllocator`, and the Triton
  extend/decode consumers. Implemented a 3,580-row offline trace for global
  layers `[5,11,17,23,29,35,41,47,53,59]`. No GPU, CUDA, checkpoint shard,
  SSH, provider, endpoint, or spend was used.
- Evidence: each active token costs 4,096 E5M2 K+V bytes per global layer.
  The 357 decode forwards stage `1,812,617,748,480` exact H2D bytes; first and
  last steps contain 118,263 and 129,655 cached physical rows per layer.
  PCIe Gen4 x16's candidate-favorable payload ceiling is
  `31,507,692,307.69 B/s`, giving `57.529372` batch-seconds or
  `1.797792871875 s/request` before every additional term. At `$1.10/h`, the
  H2D-only floor is `$549.3256/M requests` versus the `$451.4966` target.
- Memory: replacing the corrected 5,312,020,480-byte global device pool with
  two 531,202,048-byte staging buffers saves 4,249,616,384 bytes before new
  metadata. Complete required memory spans 48,073,652,020–49,029,621,260
  bytes versus 48,305,799,168 exposed, so only the candidate-favorable end
  fits; latency is independently decisive.
- Decision: typed `none`. Each attention consumer waits on its staging event
  and no dependent overlap is credited. Even granting perfect overlap with
  all compute cannot beat the serial H2D resource-work floor. Six focused
  tests pass. Terminal SHA-256
  `834bbdcaf57c1762aeac1863e94f25d58bffc7f972e0f1c3e964fabffad8a5f8`;
  raw trace SHA-256
  `be1bb5687e951817d784628599e9972a9a6c54e2bc0922aacefc0d63e72c9083`.
