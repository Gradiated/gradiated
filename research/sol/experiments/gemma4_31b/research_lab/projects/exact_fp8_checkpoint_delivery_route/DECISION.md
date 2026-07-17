# Decision: typed none

No candidate clears the exact delivery contract. The strongest public candidate, `jamesleeht/gemma-4-31B-it-FP8-block-8192`, is 33,263,025,112 bytes in two shards: 46.81% below the pinned 62,546,177,752-byte BF16 checkpoint. Its producer recipe is disclosed, but its base revision is not.

The pinned vLLM source has an SM89 per-tensor FP8 path but explicitly gates block FP8 CUTLASS support at SM90. This candidate is compressed-tensors `FP8_BLOCK`, and vLLM issue [#39407](https://github.com/vllm-project/vllm/issues/39407) reports Gemma4 FP8_BLOCK repetitive output from double-applied activation scales. The smaller byte count therefore cannot be promoted to an actual SM89 consumer route.

The ModelOpt per-tensor candidate discloses base commit `419b2efe421994fdfd3394e621983d4cc511cd4f`, not the target revision, and its shard access returned HTTP 401. It is not a reproducible legal route for this campaign.

Evidence is measured metadata/HEAD response and pinned-source inspection; quality claims in candidate cards are vendor-reported only. No weights were downloaded or retained, no provider resource was touched, and no quality or endpoint result transfers. See [DELIVERY_ROUTE.json](DELIVERY_ROUTE.json).
