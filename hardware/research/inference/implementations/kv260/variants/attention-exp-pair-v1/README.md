# Two exponential units in one attention head

This is the candidate for [Experiment 13](../../../../experiments/kv260-attention-exp-pair-v1.md). The generator verifies and materialises the adopted attention-exp-div-v1, then replaces only its attention controller. It instantiates the same checked exponential implementation a second time with its operation fixed to exponential. The model loader writes the two copies of the table together.

One score read port fetches the adjacent pair in two clocks. Both commands start together. The original write port stores the two results on successive clocks in score order, retaining a completed second result until needed. An odd tail uses only the first unit. On a first-unit fault the controller consumes any pending second result before returning an error. Reset cancels the controller and both units. Score, probability and cache ordering are preserved.

Use materialise_attention_pair.py to generate both arms. replay_pair.py takes the pinned Verilator installation, the prior simulation archive extracted on the Mac, and the independent serial traces. test_directed.py uses the same model table and known mixed cutoff cases. The completed run records identify all inputs by hash.
