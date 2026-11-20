# Cartridge serving plan

A **cartridge** is a trained block of input embeddings that a task version
places in front of the prompt. It adapts a base model without changing its
weights, like a long learned system prompt. Task versions can be served as a
cartridge instead of a PEFT LoRA adapter. Many cartridges share one deployment,
and each request may use a different one.

## Artifact

One safetensors file, `cartridge.safetensors`, with no pickled data:

| Tensor | Shape | Type | Meaning |
| --- | --- | --- | --- |
| `embeddings` | `[K, hidden_size]` | bf16 | One learned input embedding per cartridge position |
| `slot_token_ids` | `[K]` | int64, optional | Token IDs the cartridge was trained behind, for models that hash token IDs (DeepSeek V4 Engram) |

The safetensors header metadata holds `format` = `gradiated.cartridge/1`,
`placement` = `system_prompt_start` and, optionally, `separator`, the text that
followed the slots in training (default `"\n\n"`).

`K` may be any size from 1 up to, but not including, the base model's maximum
context length. Upload rejects anything larger. `hidden_size` must equal the
base model's embedding width, and every value must be finite.

## Contract

`TaskVersionAdapterSchema` becomes a union on `format`:

- `peft_lora`: unchanged.
- `cartridge`: `artifact_uri`, `sha256`, `size_bytes`, `num_tokens` (K),
  `hidden_size`, `placement`, `separator`, `has_slot_token_ids` and the existing
  optional base-revision fields.

`task_versions.adapter` is already untyped `jsonb`, so no SQL migration is
needed. Code that reads LoRA-only fields such as `rank` narrows on `format`.

## Upload

`POST /model-uploads` accepts `format: "cartridge"` with one file grant,
`cartridge.safetensors`, instead of the LoRA config and weights pair. Completion:

1. reads the safetensors header without loading the tensors, and checks the
   names, dtypes, shapes and metadata above;
2. rejects `K >= max_context_length` of the base model;
3. streams the values to check they are finite;
4. stores the file at `cartridges/<upload_id>/<sha256>/cartridge.safetensors`
   and publishes an `unavailable` version.

There is no console upload UI yet; staff use the API.

## Serving (SGLang)

Cartridges reuse SGLang's multimodal precomputed-embedding path instead of
patching the embedding layer:

- **Resolution.** The tokenizer manager's adapter resolver returns
  `kind: "cartridge"`. The adapter loader downloads, verifies and caches the
  file, and registers it in a GPU **cartridge pool** keyed by its sha256. The
  pool is bounded by `--cartridge-pool-bytes` and evicts the least recently used
  cartridge with no running requests.
- **Placement.** After the chat template is rendered, the tokenizer manager
  inserts K placeholder positions, plus the separator tokens, at the start of
  the system prompt, adding an empty system message when the request has none.
  The cartridge becomes one multimodal item with precomputed features whose
  identity is the cartridge sha256.
- **Isolation and caching.** SGLang replaces an item's placeholder positions
  with pad values derived from its identity. The radix cache therefore shares a
  cartridge prefix between requests that use the same cartridge, and never
  between different cartridges. Customer text cannot produce pad values, so
  only the inserted positions receive cartridge embeddings.
- **Embedding.** The model's existing multimodal embedding routine writes the
  cartridge rows at those positions; DeepSeek V4.1 already uses it for vision.
  When `slot_token_ids` are present, Engram hashes those IDs at the cartridge
  positions, so serving matches training.
- **Speculative decoding.** DSPARK draft layers read the target model's hidden
  states, and their own embedding lookups must use the same cartridge rows.
  Qualification runs with speculative decoding on.

### Mixed batches cost nothing extra

A batch may hold requests for any number of different cartridges, and
requests without one, at the same throughput as the same batch without
cartridges. This is the main advantage over LoRA, which adds adapter matmuls
to every token, every layer and every decode step.

- **Decode:** no cartridge work at all. After prefill a cartridge is ordinary
  KV cache, so decode kernels, CUDA graphs and batch sizes are unchanged.
- **Prefill:** one gather of each cartridge position's row from the pool,
  written into the embedding output by index. One fused index copy per
  batch, with no per-cartridge loop, host sync or CPU work in the forward.
- **Prefix cache:** the cartridge is the prompt's first block, so after a
  cartridge's first request later requests reuse its cached KV and skip that
  prefill.
- **No limit on cartridges per batch.** Unlike `max_loras_per_batch`, the
  scheduler never splits or delays a batch because of cartridges. The pool only
  bounds how many cartridges are resident on the GPU at once.
- **Nothing is turned off for cartridge requests:** chunked prefill, overlap
  scheduling, CUDA graphs, DSPARK and HiCache all stay on. The multimodal path
  can disable some of these for real multimodal inputs. The patch has to check
  each one and keep it on for cartridges, which have no encoder to run.

**Acceptance benchmark.** The runtime PR has to show these numbers on the
production DeepSeek V4.1 Flash configuration:
- decode throughput and inter-token latency for a batch of 64 requests across
  64 different cartridges, within 2% of the same batch without cartridges;
- prefill throughput with cold cartridges, within the cost of K extra prompt
  tokens;
- prefill throughput with warm cartridges, matching the uncached prompt suffix
  alone.

The change is carried as a bundle patch shaped for upstream: a cartridge
resolver, the pool, template-time insertion and the Engram ID override.

## Gateway and billing

- `ADAPTER_QUERY` returns `format` and `num_tokens`. Cartridge versions route
  only to deployments whose release sets `cartridge_enabled`.
- The request's context limit is the model's limit minus K.
- Cartridge positions are not billed: usage reports and billing subtract K from
  prompt tokens and from cached prompt tokens.
- `served_digest` includes the format.

## Qualification

Promotion probes each serving allocation, as for LoRA, and also sends a fixed
canary prompt with and without the cartridge. The cartridge passes only if the
first-token logits differ by more than a set threshold, which catches a
cartridge that loads but is never applied.

## PR stack

1. This plan, the contract union, cartridge upload validation and an API
   upload path (no UI).
2. The adapter loader: cartridge download, verification and caching.
3. The SGLang bundle patch: resolver, pool, insertion, Engram IDs and DSPARK.
4. The runtime flag and `cartridge_enabled` release field.
5. The gateway: query, routing, context limit and billing.
6. Qualification: the with-and-without canary.
7. Console labels for cartridge versions.

One customer version was inserted by hand before this work, with a placeholder
`peft_lora` adapter pointing at a research checkpoint. The checkpoint has been
converted to `cartridge.safetensors` and stored next to it. Once PR 1 is
deployed, the row's adapter is rewritten to the `cartridge` format, which older
code cannot parse.
