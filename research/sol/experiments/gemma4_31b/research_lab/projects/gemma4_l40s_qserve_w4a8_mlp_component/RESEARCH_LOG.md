# Research log

## 2026-07-24 — fixed SM89 QServe W4A8 packet ready

- Question: can QServe progressive group-128 W4A8 replace the measured resource-heavy Marlin decode MLP schedule on L40S?
- Action: pinned OmniServe/QServe `02b2925aa6fa3b92b06316a1524b7f38922cd9c8`; bound its SM89-supported low-M `32x64x128`, four-warp, three-stage GEMM; implemented the exact checkpoint-free Gemma gate/up–tanh-GELU-and-quant–down chain, independent dequantized-W4 oracle, and actual SGLang online-FP8 control.
- Evidence: `MECHANISM_BINDING.json` and immutable `GPU_INPUT_MANIFEST.json`. The executed GEMM differs from the pinned upstream bytes only by removing four trailing spaces. Local AST/JSON/shell/hash checks and DevEx checks pass. The fixed source schedule uses 24,960 dynamic shared-memory bytes and 128 threads; exact grids are 672 gate/up blocks (4.7324 L40S waves) and 84 down blocks (0.5915 waves). Compulsory W4 weight bytes are 173,408,256 versus 346,816,512 for FP8.
- Interpretation: the gate/up path should escape Marlin's measured 200-register, 233,472-byte, one-wave collapse; down remains grid-underfilled and is the main falsifier. Registers, spills, numerical correctness, and warm latency remain target-GPU measurements, not offline claims.
- Next: the director should provision and register one L40S bench from `PROVIDER_REQUEST.json`. Claim it only after registration, then run the immutable packet once and retain compile resources, all eight correctness/timing rows, and candidate-path evidence.
