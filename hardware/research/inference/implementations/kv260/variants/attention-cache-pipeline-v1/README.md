# Overlap cached reads and attention arithmetic

Attention requests the next cached word while multiplying and accumulating the current word. Each response still supplies the operands in the original order. A refused read becomes an ordinary request for the same address. The original scalar work and single outstanding cache interface stay fixed.

`materialise_attention.py --arm control|candidate --output /path/to/new/rtl` regenerates the exact adopted control and the attention-only candidate. The [experiment protocol](../../../../experiments/kv260-attention-cache-pipeline-v1.md) explains the controls and preregistered cycle law.
