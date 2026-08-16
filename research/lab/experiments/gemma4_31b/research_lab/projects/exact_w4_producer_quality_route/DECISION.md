# Decision: typed none

The strongest current W4 candidate is `ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` at HF commit `a3b96c7a8d07cc84cae0f0261ac2574310b12d37`. Bounded public metadata measures one 19,188,422,752-byte (17.871 GiB) safetensors file. Its config binds compressed-tensors `pack-quantized`, asymmetric INT4, group size 128, int8 zero-points, and BF16/FP16 activations; the recipe leaves the tied `lm_head`, vision tower, and projector unquantized. Derived staging is 15.4–153.5 seconds at 10–1 Gbps before storage/verification overhead.

Pinned vLLM source inspection shows the compressed-tensors WNA16 scheme can select `MarlinLinearKernel` for supported devices, so representation/loader compatibility is plausible. This is first-party source evidence, not a CUDA result; no six-shape execution, tied-head request, model load, quality run, or 10K fit was performed.

The route is rejected because the candidate only says `base_model: google/gemma-4-31B-it`; it does not bind the required base revision `b9ea41a2887d8607f594846523f94c6cc75ac8a4`. Its producer is described as `llm-compressor main, post-0.10.0.1`, and its calibration dataset names have no immutable revisions, file hashes, order, or seed. Therefore the compressed bytes cannot be proven to derive from the exact target, and no quality claim transfers. The cheapest missing fact is an immutable derivation manifest containing those identities plus output shard/index hashes.

The later falsifier is retained in [ROUTE_DECISION.json](ROUTE_DECISION.json): fresh-process pinned-vLLM Marlin execution, raw serialized outputs, exact chat/stop behavior, 4,214/358 and 10K text-only cases, local/global attention probes, and logits/features against the exact BF16 revision. It is specified, not passed.

Evidence labels: HF sizes/config/commit are measured metadata; recipe and card statements are community/vendor claims; vLLM behavior is first-party source inspection; staging times and compatibility interpretation are derived/inferred. No weights, GPU, provider, or quality execution occurred.
