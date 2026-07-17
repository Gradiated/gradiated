# H100 SGLang capacity decision

**Typed none:** do not create an H100 owner for the immutable command. Although raw 80 GB HBM has c1 room, the pinned SGLang source reduces `mem_fraction_static` for this multimodal model even with text-only requests. Its resulting weights-plus-KV cap is 55.851 GiB, while the exact BF16 checkpoint is 58.251 GiB: a 2.399 GiB shortfall before the first KV page.

The binding implementation also uses 16 KV heads × 256 dimensions for both local and full layers, not the older generic global-head geometry. That makes primary peak FP8 KV 0.751 GiB/request and 10K peak 1.199 GiB/request including a conservative scale sensitivity, but those values do not affect the c1 close.

The market hurdle is still 1.118–1.402 completed requests/s (1.252 at $2.80/hour and $0.000621/request). The packet's 1.825-rps floor is independently 1.457× stricter at that base case; its missing 31.37% derate provenance cannot be attributed to the market hurdle. Neither this cost reconciliation nor the matched 10% vLLM gate rescues an unloaded server.

See [CAPACITY_COST_BOUND.json](CAPACITY_COST_BOUND.json) for source binding, the raw/configured/conservative surface, and the close condition. A future route must materially change and rebind configuration (such as a language-only option) before any provider admission; this screen does not nominate H200.
