# Four bits per multiply step

This variant inherits prefill-skip-v1. Only the generated `fixed_scalar.sv` changes. The circuit still uses AU02, so the image's SHA-256 identifies the physical arm. All five scalar arithmetic units use the same implementation. Dense matrix arithmetic is outside this change.

The multiplier takes magnitudes and remembers the output sign as before. Let `a` and `b` be the magnitudes and let `R` start at `b`. On each of 16 steps it consumes the bottom four bits. It adds `a * (R & 15)` to the upper half of `R` and then shifts the combined value right by four bits. After `k` steps, `R = floor(b / 16^k) + a * (b mod 16^k) * 16^(16-k)`. Therefore after step 16, `R = a * b`. The extended upper sum has 68 bits, enough even for arbitrary unsigned 64-bit operands since `(2^64-1) + 15*(2^64-1) < 2^68`. Keeping all 68 bits before the shift preserves the carry and reconstructs the full 128-bit product. The original magnitude limit, sign application and error path remain in force. The same recurrence serves direct products, EXP interpolation and all six products of an RSQRT command.

From this directory, use `materialise.py --output /path/to/new/rtl`, `test_model.py --help` and `test_scalar.py --help`. The full-circuit profile uses the existing pinned prefill-skip simulation archive to recover model words, score references, cache comparisons and exact control cycle counts. The scalar test consumes those same model words and checks both variants against the existing independent integer oracle, including cancellation in every multiply step.

[Experiment protocol](../../../../experiments/kv260-scalar-mul-v1.md)
