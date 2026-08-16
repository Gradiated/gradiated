# Decision

Terminal result: **typed `none`**.

The exact checkpoint has 356 vision-exclusive tensors totaling 1,151,487,072 bytes (1.072406 GiB): 1,139,100,768 bytes in `vision_tower` and 12,386,304 bytes in `embed_vision.embedding_projection`. The prior 3.752517-GB residual cannot be removed wholesale because it also contains non-vision remainder.

The pinned runtime selects `Gemma4ForConditionalGeneration`, whose constructor always creates the vision tower and projector and whose loader has no text-only omission gate. `Gemma4ForCausalLM` is a separate source path that skips multimodal prefixes, but changing the exact checkpoint to that path is an unmeasured intervention, not current unload behavior.

Even granting the full exact unload, W4 resident weights fall only from 20.343494 to 19.271088 GiB. With the inherited 5-GiB runtime reserve and source-bound FP8 KV, primary c1/c2/c4/c8 are 24.634511/24.997934/25.724781/27.178473 GiB; the 10K values are 24.856954/25.442820/26.614552/28.958015 GiB. These all exceed the conservative 22.08-GiB envelope for a nominal 24-GiB card; c1 also exceeds nominal capacity before allocator rounding.

No direct nominee is emitted. A future route would require a new text-only architecture/config adapter, exact raw output/logit comparison, and a larger-memory or lower-reserve representation; vision eligibility would be explicitly forfeited.
