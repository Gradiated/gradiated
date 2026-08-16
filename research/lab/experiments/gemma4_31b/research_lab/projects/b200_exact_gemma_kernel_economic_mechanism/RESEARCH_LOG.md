# Research log

## 2026-07-17 — director admission

Activated as a materially different `$0` deep placement/kernel line. Canonical prices are fresh: B200 `$5.15/hour` versus H100 `$2.80/hour`; B200 must justify at least `1.8392857×` price-normalized throughput before endpoint overhead and quality.

## 2026-07-17 — exact SM100 mechanism and direct falsifier

Question: does pinned B200 source and exact Gemma geometry justify one direct test despite the price premium? Action: traced the immutable vLLM NVFP4 producer/operator chain through SM100 CUTLASS source, derived all 24 six-shape M8/M16/M32/M3679 tile/grid/payload rows, and joined fresh prices with measured H100/H200 boundaries. Evidence: all K/N dimensions are divisible by 256; decode uses 128-wide N tiles with only 42 CTA slots for three shapes at M8/M16, while M3679 supplies 630–5,040 logical SM slots. Native NVFP4 plus scales is `0.5625` byte/parameter; ideal B200/H100 FP8 priors are `4.245×` for decode weight streaming and `4.548×` for prefill compute, versus the `1.839×` price hurdle. The impossible B200 NVFP4 linear floor is `0.116529/0.070281/0.047157 s/request` at c8/c16/c32, below the absolute `0.297928 s/request` ceiling, so typed none is not supported. Interpretation: nominate one cold-cache, exact-shape, checkpoint-free native-NVFP4 component falsifier; the tied head remains BF16 and attention has only thin bandwidth-derived margin. No provider/GPU/compile/checkpoint work occurred. Artifact: `MECHANISM.json` (`sha256:0ced5b18806b14f6fd0070f00c52640af5e9764886fed46752da43028f8b1119`).
