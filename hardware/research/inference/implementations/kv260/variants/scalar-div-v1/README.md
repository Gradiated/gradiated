# Two bits per divide step

This variant keeps the scalar-mul-v1 sources and changes only generated `fixed_scalar.sv`. The board interface is still AU02. The control and candidate are identified by their separate firmware pins.

A restoring divider keeps the remainder from the bits processed so far. On each clock, this implementation appends the next two input bits. For divisor `B` and remainder `r`, the trial is `4r + next_bits`. Since `0 <= r < B <= 2^62`, the trial fits in 64 bits, is strictly less than `4B`, and the greatest fitting one of `0, B, 2B, 3B` determines the next two quotient bits. Each subtraction is zero-extended to 65 bits, so bit 64 indicates borrow. The chosen nonnegative remainder again satisfies `r < B`. At the end the raw quotient and remainder match ordinary integer division. Round once using the registered remainder and quotient parity, then restore the sign and enforce the original result range. Internal table operations receive the same raw remainder where needed. The divider now executes 32 calculation clocks and one finish clock.

Use `make_division.py --output /path/to/fresh/rtl` to generate the sources. The test scripts reuse the pinned scalar-mul archive and the existing scalar integer oracle. See the [protocol](../../../../experiments/kv260-scalar-div-v1.md).
