# Output-projection weights in LUTRAM

This variant changes the implementation directive for the 32 × 32 output-projection weight matrix. It keeps the existing registered read, load constraints and arithmetic. Use the pinned materialiser with an explicit arm and a fresh output directory. [Experiment protocol](../../../../experiments/kv260-output-projection-lutram-v1.md)
