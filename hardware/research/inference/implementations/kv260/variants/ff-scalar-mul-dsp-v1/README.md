# Five-cycle feed-forward scalar multiplication

[Experiment 19](../../../../experiments/kv260-scalar-product-opportunity-v1.md) starts from the 50 MHz `probability-div-v1` circuit. The materializer verifies all eleven inherited RTL source pins. It replaces the multiplier used by the single feed-forward scalar instance in `feedforward.sv`. The two feed-forward dense input projections and the down projection retain their own multiply-accumulate units. Attention and normalization retain their scalar instances.

## Exact product and schedule

The scalar takes the unsigned magnitudes A and B and stores the output sign as the XOR of the input signs. Each magnitude has four unsigned 16-bit limbs. Each partial product `a[i] * b[j]` is at most `65535²`, so its low 32 bits contain the full result. The logic zero-extends both limbs to positive signed 17-bit operands before multiplication. This fits the signed 27 × 18 inputs of one DSP48E2 slice. The synthesis attributes request a DSP for each of the 16 limb products and fabric carry logic for the registered sums. The routed implementation establishes the actual DSP count and clock slack. [AMD DSP48E2 documentation](https://docs.amd.com/r/en-US/ug974-vivado-ultrascale-libraries/DSP48E2) · [Vivado synthesis attribute](https://docs.amd.com/r/en-US/ug901-vivado-synthesis/USE_DSP)

| Calculation clock | Registered work |
| ---: | --- |
| 1 | All 16 limb products |
| 2 | Four 80-bit rows, each multiplying A by one limb of B |
| 3 | Two 96-bit sums, each multiplying A by one half of B |
| 4 | One 128-bit magnitude product |
| 5 | Magnitude range check, sign application and return to the caller's state |

For row j, each partial product carries weight 2^(16i). The i = 0 and i = 2 terms occupy disjoint 32-bit fields. The i = 1 and i = 3 terms occupy a second pair of disjoint fields, shifted by 16. The sum of the two concatenations gives A times limb j and fits in 80 bits because A < 2^64 and limb j < 2^16. Adding consecutive rows after shifting the second by 16 gives each half-product, which fits in 96 bits. Shifting the upper half-product by 32 and adding the lower gives A × B, which fits in 128 bits. Each addition therefore has space for its complete carry.

The finish stage rejects every absolute product above 2^63 − 1, including a would-be negative result with magnitude 2^63. It applies the original sign rule to accepted products. This preserves both the observable overflow rule and the result for signed-minimum operands. The same path serves explicit multiplication and the scalar's internal exponential interpolation and reciprocal square root. Division, rounding, table loading, dispatch, stalls, and error packet handling use the inherited RTL. One operation owns the multiplier through retirement. Reset abandons in-flight data. Each pipeline register is assigned for the next operation before the controller can read it.

## Reproduction

Use Python 3.10+ and the pinned Verilator 5.052 toolchain. `materialise_partial_multiply.py` generates the two full RTL source sets. `test_scalar.py` takes the frozen model hex file and tests the exact signed scalar interface with both real multipliers. `replay_multiply.py` takes the sealed Experiment 18 simulation archive and checks the seven full-model cases, all completed feed-forward products against Python integers, all occupied-depth wait clocks, cache traffic, outputs, scores and terminal geometry.
