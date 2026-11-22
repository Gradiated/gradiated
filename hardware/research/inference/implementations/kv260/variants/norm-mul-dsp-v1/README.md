# Five-cycle multipliers for three normalization stages

[Experiment 20](../../../../experiments/kv260-norm-mul-dsp-v1.md) starts from the routed `ff-scalar-mul-dsp-v1` circuit. The source generator verifies all eleven adopted RTL files. It changes `rmsnorm.sv` to instantiate a local scalar that reuses the [Experiment 19 partial-product datapath](../ff-scalar-mul-dsp-v1/README.md#exact-product-and-schedule). Norm1, norm2 and normfinal each instantiate a dedicated copy. The general `fixed_scalar.sv` and the feed-forward and attention source files retain their original pins.

The normalizer calls its scalar for 32 input squares, 32 input-by-inverse products and 32 gain products. The reciprocal square root runs two Newton iterations of three products each. Each normalization therefore issues 102 exact products. The three normalizations run in separate transformer phases. The last normalization completes before the decision to skip a vocabulary projection, so skipped prefills still run all three.

The new multiplier registers sixteen 16-by-16 unsigned limb products, represented by positive signed 17-bit operands. Its registered 80-bit rows, 96-bit halves and 128-bit sum carry all bits through to the original magnitude check and sign handling. Each accepted operation occupies the five states before return. An overflow still rejects every magnitude above 2^63 − 1. Division, shifts, reciprocal-square-root control and tables use the inherited scalar algorithms. The instance wrappers retain their existing ready and valid handshake. Reset cancels each pending operation, and a new command writes the pipeline data before consuming it.

Each product saves 11 clocks. With 102 products in each normalization phase, the prediction is 1,122 clocks per phase and 3,366 clocks per processed position. The RTL replay checks the actual contributions per phase and the prefix, first-byte, last-byte and completion counts independently.

## Reproduction

Use Python 3.10+ and the pinned Verilator 5.052 toolchain. Run `materialise_norm_multiply.py` to generate each RTL arm. Run `test_directed.py` with the frozen model hex file for independent scalar arithmetic, output stalls and cancellation in all five states of each nested reciprocal-square-root product. Run `replay_norm.py` with the pinned Experiment 19 simulation archive. It checks seven exact cases including the 256-position context, each ordered normalization product and output, cache checkpoints and model score streams.
