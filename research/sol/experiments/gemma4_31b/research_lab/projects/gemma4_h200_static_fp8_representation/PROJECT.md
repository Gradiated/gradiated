# Static FP8 representation frontier on H200

## Question

Can a deployable calibrated/static FP8 weight-and-activation representation outperform the retained dynamic in-memory FP8 endpoint by removing repeated activation scaling and selecting a better exact-shape GEMM path?

## Why this is distinct

The retained frontier dynamically quantizes activations and spends measured time in per-token quantization. The failed ModelOpt project calibrated the model but failed at its historical HF export boundary; the current vLLM experiment retained BF16 weights. Neither result measures a native static-FP8 endpoint in a runtime that can actually consume the representation.

## Immediate experiment

Use the exact checkpoint/workload identities from `../gemma4_h200_v0513_fp8_qkv_residual_profile/BINDINGS.json`. Select the shortest current producer/consumer route—SGLang compressed-tensors, TensorRT-LLM/ModelOpt engine export, or a minimal content-addressed safetensor overlay with explicit scales—and produce one exact H200 component or endpoint result. Reuse the successful calibration artifacts when sound. Implement an ordinary missing serializer or loader binding in place rather than treating the old export failure as scientific closure.

Measure real weight consumption, activation-quantization work removed, GEMM selection, numerical sanity, memory, and one c32 endpoint pair when runnable. Keep QKV and deferred local-KV changes in the matched control/candidate where compatible. Do not run broad quality evaluation before a performance survivor, and do not substitute BF16 weights while calling the result static FP8.

## Resources

- One director-registered retained H200, shared with compatible runtime work when practical.
- The campaign has only `$1.80` unreserved: prepare producer/loader integration offline and use at most 40 H200 claim minutes/`$1.80` for the first exact real-consumer component and any conditional endpoint continuation that fits the same cap.
- Researchers do not create or destroy provider resources.
