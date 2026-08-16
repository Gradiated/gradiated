# Decision — FP8-KV c8 retained arm

The pinned vLLM revision supports an explicit execution-equivalent route for
Ada: `--kv-cache-dtype fp8_per_token_head`. It stores native Ada FP8 E4M3
bytes and computes per-token/head FP32 K/V scales at cache-write time. The
ordinary `fp8`/`fp8_e4m3` path is not admissible for this packet because the
exact Gemma checkpoint has no K/V scale tensors, so the pinned scalar path
falls back to scale `1.0`; that scale identity is not a safe correctness
contract for Gemma 4.

Using the exact hybrid geometry, inline scale bytes raise FP8 c8 KV from the
ideal half-size to 4.470 GiB for eight primary requests. Adding the existing
34.35 GiB conservative weights/scales bound and 5.0 GiB runtime reservation
gives 43.820 GiB, leaving 0.884 GiB under the 44.704 GiB usable envelope. The
10K single-stream derived total is 40.131 GiB with 4.573 GiB headroom. These
are derived bounds, not CUDA measurements.

`FP8_KV_ARM.json` is therefore start-ready conditional evidence, not a
scientific result. It may run only after the stock arm produces the registered
correctness/c4/c8-or-cost trigger, and only by restarting the same retained
server under the existing owner. The first probe and the complete c8 result
must be consumed through raw token IDs, memory, telemetry, and cleanup gates.
Any scale/backend ambiguity, token mismatch, incoherence, OOM, timeout,
reload, or false trigger closes the arm immediately.
