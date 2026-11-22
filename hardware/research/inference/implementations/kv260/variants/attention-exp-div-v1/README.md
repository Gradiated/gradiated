# Attention exponential division

This variant applies the existing guarded division by 45,426 to the attention-local exponential. The adopted cache pipeline, generic probability divider and remaining scalar users retain their original sources.

`materialise_attention_exp.py --arm control|candidate --output <new-directory>` regenerates the pinned source. See the [protocol and exact arithmetic bounds](../../../../experiments/kv260-attention-exp-div-v1.md).
