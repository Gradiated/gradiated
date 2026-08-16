# Minimal-depth42 exact loader falsifier

## Question

Can the clean 42-layer AWQ root cross the remaining zero-cost admission boundary by constructing the real pinned vLLM model graph and exercising its unchanged weight-loader path, or is an actual CUDA load the first honest test?

## Why it matters

The clean v2 materialization closes byte integrity, config/index/key/layer closure, and idempotence, but actual model instantiation and consumed/missing/unexpected loader sets remain unmeasured. The candidate's derived c32 throughput is only `597.529` output tok/s, `0.515%` above the authoritative `594.466`-tok/s gate, so this project must remove a real loader uncertainty quickly; another source-string, header, shape-divisibility, or manifest check has no portfolio value.

## Fixed identity and evidence

- Root: `/root/.cache/glm47flash-awq-minimal-depth42-v2-5dbf26dc16a1`, mounted or treated read-only.
- Semantic contract SHA-256: `5dbf26dc16a1cabbdb36eb256a996a11cf44c71c702b72686806a68a3bb1a290`.
- Runtime manifest SHA-256: `cfee71f350b69a931bc6700712db9850780c30f2e8aa51a406ce9ac7a668cdda`.
- Checksum-list SHA-256: `87d080fa3b10a184abf39e050f6dd67264b32394b43d45caecd93d32e3512950`.
- Exact index: 24,615 keys and `16,654,390,736` tensor-payload bytes over four weight shards.
- Runtime: local `glm-vllm:0.15.0-transformers-1618d44` image and the same pinned GLM/vLLM/compressed-tensors code used by the measured current-AWQ service.
- Prior student39 evidence establishes that ordinary local construction reaches `RuntimeError: No CUDA GPUs are available`; do not relabel that as loader success or repeat it without testing a materially different exact meta/fake route.

## Scope

Run exactly one bounded local falsifier at `$0`. Use the real pinned registry, `Glm4MoeLiteForCausalLM` constructor, quantization-method selection, model parameter graph, `load_weights`, and `AutoWeightsLoader` implementation. A project-local probe may redirect tensor allocation to meta/fake storage only if it does not replace or monkeypatch loader, quantization, dispatch, name mapping, parameter semantics, or the model's load entrypoint. Derive names, shapes, and dtypes from the exact safetensors headers; do not read or copy 16.7 GB of payload merely to force a pass.

A pass requires all of the following:

1. the exact registry resolves the production model class and compressed-tensors selects the WNA16/pack-quantized route without fallback;
2. the exact 42-layer config constructs the real model parameter graph;
3. the real load entrypoint consumes all 24,615 header-derived names/shapes/dtypes and returns a source-defined loaded set with no unexplained missing or unexpected keys;
4. any source-defined exemptions are preregistered before execution; and
5. deleting one real key and injecting one foreign key both fail with typed diagnostics, proving the result is not a hard-coded count comparison.

Fail closed as `GPU_REQUIRED` as soon as exact construction or load reaches unavoidable CUDA/platform initialization, exceeds the resource cap, or would require changing the loader/quantization/parameter semantics. That is a useful terminal result: it ends local preparation and leaves a later direct L40S load as the only honest admission test.

Do not touch the active near-stock service, provider inventory, shared launcher, shared remote script, checkpoint payloads, or any root outside project-local artifacts. Do not use CUDA, network access, training, inference, quality evaluation, provider mutation, or controller work. If the full-model r3 result becomes a valid economic pass before this project begins, close without execution because student42 is no longer decision-relevant.

## Budget, stop rule, and portfolio branch

Maximum wall time is 900 seconds, maximum peak RSS is 8 GiB, and maximum new artifact size is 64 MiB. One attempt only; no successor preflight. Stop after one exact pass, one typed `GPU_REQUIRED`/resource-bound result, or the full-model supersession branch.

Neither a pass nor `GPU_REQUIRED` authorizes provider spend. After r3 terminates, admit the clean student42 identity to one direct L40S c16/c24/c32 measurement only if full-model FP8 c32 OOMs, is invalid, or completes below `594.466` output tok/s. If full-model FP8 c32 passes the economic gate, park student42.

## Artifact contract

Produce one compact JSON binding runtime/source/config/index hashes, constructor and quantization selections, loaded/missing/unexpected set counts and hashes, both negative controls, peak RSS, elapsed time, and a typed decision; include only focused project-local probe/tests and a concise `RESEARCH_LOG.md` update.
