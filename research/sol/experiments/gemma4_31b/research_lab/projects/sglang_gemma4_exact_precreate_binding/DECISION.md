# Decision: start packet emitted

The exact SGLang route clears the `$0` binding and CPU-safe validation gate. Docker Registry metadata resolved `lmsysorg/sglang:dev-gemma4` to manifest-list digest `sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427` and an amd64 child digest without pulling layers. The named support commit is immutable and contains Gemma 4 model/config/CLI support.

The pinned Hugging Face revision is bound by SHA-256 hashes for config, tokenizer, tokenizer config, chat template, and processor metadata. The CPU validator passed AST parsing and exact geometry checks: 60 layers (50 sliding, 10 full), 1,024 sliding window, BF16, 32/16 attention/KV heads, four global KV heads, zero shared-KV layers, and 262,144 vocabulary. Source inspection confirms the shared-KV path, Gemma 4 registration, `fp8_e5m2`, served-model identity, metrics, and cache-report hooks. Reasoning remains disabled by leaving `reasoning_parser` unset and the template's `enable_thinking` false.

`START_PACKET.json` specifies the two SGLang arms and matched pinned-vLLM control, one H100 80GB TP=1, 1,200 seconds per sequential arm, raw-output/telemetry/cleanup requirements, the H100 `$2.80/GPU-hour` planning rate, and typed negative gates. This is a conditional paid falsifier packet, not a measurement or quality result; no provider mutation occurred.

The next authorized owner must re-resolve the image manifest immediately before create, stage the exact revision without accepting a mutable tag, and reject the run on any listed identity, capacity, telemetry, quality, or cost gate.
