# Parallel final token-score lanes

Two or four lanes accumulate independent output rows, sharing a single activation read and taking one weight per lane from row-interleaved banks. Rounding is unchanged and scores leave in the original order. One stalled score holds the current group in place.

Generate the exact original one-lane or a specialised arm with `materialise_lanes.py --lanes 1|2|4 --output /path/to/fresh/rtl`. See the [experiment protocol](../../../../experiments/kv260-logits-lanes-v1.md) for the pinned fixtures and separate simulation, routed and physical gates.
