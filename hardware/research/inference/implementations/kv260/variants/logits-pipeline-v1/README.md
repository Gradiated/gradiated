# Final token-score pipeline

This variant can read the next input and weight while its single multiply-and-accumulate lane uses the previous pair. It starts each row with one synchronous read. The final multiply is followed by the existing round and output steps. A stalled output still prevents starting the next row.

Only the final vocabulary projection selects the specialised module. The other dense instances keep their previous source and schedule. The model, arithmetic, memory layout and AU02 host interface are inherited from scalar-div-v1.

Generate all pinned RTL with `materialise.py --output /path/to/fresh/rtl`. Use `test_model.py` to check both full-model arms against the pinned scalar-div simulation archive. Use `test_component.py` for arithmetic, cycle scheduling, output stalls and reset. Enable Verilator assertions and use the pinned simulator in the [experiment protocol](../../../../experiments/kv260-logits-pipeline-v1.md).
