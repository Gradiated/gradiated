# Decider v1.2 27B runtime

Native, text-only SystemOne serving for `perplexity-ai/pplx-decider-v1.2`.
The catalog is initially unavailable; enable it with qualified local capacity.
There is no OpenRouter mapping or external fallback for this model. Customer
training is not exposed by this runtime.

The Apache-2.0 checkpoint and loader are pinned to
`cce0f3f80033e9d89d80831d5281fd72124aacce`. Build-time source downloads are
hash-verified; the bundle retains LICENSE, NOTICE and modification notices.
Runtime checkpoint downloads use that immutable revision and do not execute
checkpoint Python code. `source.json` pins the loader separately from weights.

The loader adaptation quantizes exactly 192 decoder MLP projections to NF4 with
double quantization and BF16 compute. Full attention, recurrent attention,
vision parameters and the decision head stay BF16. The runtime asserts every
converted module path and count. Non-causal full attention and per-question
marker readouts remain the upstream implementation. This is mixed precision,
not a uniformly four-bit checkpoint. The upstream optional fast path is disabled.

One process admits one request, with no queue, using Kev's bounded ASGI adapter.
The 8,192-token limit includes the entire state, questions and template markers.
Over-length joint requests are rejected before inference; upstream recursive
question splitting is not used. Images and media URLs are not accepted; structured
state is serialized to JSON text. Usage counts all input tokens, reports no cache
hits and zero generated tokens. GPU errors fail health until the runtime restarts.
The server binds loopback and relies on the host proxy for external authentication.

Start through `bundles/decider-27b/entrypoint`, with the fleet-assigned GPU UUID,
`GRADIATED_RUNTIME_ROOT`, `RUNTIME_PORT` and writable `HF_HOME`. Reserve one L40S,
8 CPU, 64 GiB RAM and at least 100 GB disk for the runtime and approximately 52 GB
checkpoint. A ready process has loaded weights and warmed choice, noul and score.

The initial synthetic B300 preflight measured 27.53 GiB peak allocated GPU memory
(28.55 GiB reserved) at 7,288 input tokens. Four cases with three repeats matched
the BF16 selected choices; the largest probability delta was 0.032716. This is a
smoke test, not broad accuracy or L40S performance qualification. The earlier
broad-linear NF4 trial failed the 0.05 probability-delta gate at 0.074163.
Source, locked dependencies and raw outputs are retained at
`s3://gradiated-prod-model-artifacts-873716897517/experiments/decider-v1.2/2026-11-10-90ea3018/`.

The catalog price is $0.02/M input tokens (20 nano-USD/token), matching
[Perplexity's published rate](https://docs.perplexity.ai/docs/getting-started/pricing#decisions-api-pricing).
Cached-input pricing is the same because this runtime has no prefix cache.
Keep Kev serving until the new L40S replica passes SDK qualification and
deployment-pinned decision requests.
