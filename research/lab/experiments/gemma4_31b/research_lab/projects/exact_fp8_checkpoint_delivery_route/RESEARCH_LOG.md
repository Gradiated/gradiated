# Research log

## 2026-07-17 — director delegation

Activated as an independent `$0` line while the paid vLLM-consumer bridge runs. The immediate result is one content-addressed smaller checkpoint/runtime delivery route or a typed negative, not another readiness packet. It cannot download full weights, mutate the provider, delay the paid lane, or transfer quality. Budgets are 60 wall minutes, 1 local CPU-hour, 2 GiB storage, 512 MiB bounded transfer probes, and `$0`.

## 2026-07-17 — typed none after bounded metadata/source search

Question: does an exact, legally usable, content-addressed smaller checkpoint have a supported SM89 consumer?

Action/evidence: queried first-party Hugging Face metadata and manifests, compared config/index/tokenizer hashes, inspected the pinned vLLM commit, and issued bounded Range/HEAD probes without downloading weights. The public James/RedHatAI FP8_BLOCK candidate is 33,263,025,112 bytes across two shards versus 62,546,177,752 BF16 bytes, a 46.81% reduction. Its producer recipe is disclosed, but its base revision is not. Pinned vLLM source exposes SM89 per-tensor FP8, while `cutlass_scaled_mm_supports_block_fp8` requires SM90+. The candidate is FP8_BLOCK; vLLM issue #39407 also reports Gemma4 FP8_BLOCK scale double-application and repetitive output. The ModelOpt candidate discloses a different base commit and returned HTTP 401 for shard access.

Interpretation: byte reduction is real metadata evidence, but no candidate has both explicit target provenance and an actual supported SM89 consumer. The followed range attempt stopped after 290,816 bytes with curl exit 23; this is transport-only evidence and not a model result.

Next move: none in this project. A later paid route may revisit a first-party producer/runtime pair only after exact revision binding and an SM89 execution-equivalent consumer are available. See `DELIVERY_ROUTE.json` and `DECISION.md`.
