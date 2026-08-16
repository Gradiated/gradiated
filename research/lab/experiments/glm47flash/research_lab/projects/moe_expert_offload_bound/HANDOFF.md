# Handoff — corrected 2026-07-15

The earlier `RESULT.json` used an invalid 2,048 B/token KV envelope and is superseded for capacity decisions by [`CORRECTED_RESULT.json`](CORRECTED_RESULT.json). The correction binds the pinned vLLM MLA geometry: 54,144 B/token, 16-token blocks, 90% GPU allocation, 150 MiB redundancy, 5.799 GiB source-expected overhead, and 10 GiB conservative overhead.

Under the conservative band, 24 GiB/c8 retains 773 of 3,008 experts (25.7% hit; 32.4 tok/s PCIe-only ceiling), and 32 GiB/c8 retains 2,230 (74.1%; 93.0 tok/s). Both miss the $0.60/M target rates of 203.7 tok/s (A40), 226.9 (RTX A6000), and 356.5 (RTX 6000 Ada). 32 GiB/c16 retains 1,478 experts and reaches only 47.3 tok/s. The exact full-miss transfer is 997,991,232 bytes/token.

Decision: close expert offload for this campaign. The mechanism needs offload under the conservative memory band, but PCIe traffic falsifies the economic gate; the existing vLLM path is not a validated GLM-4.7 expert-cache implementation. Reopen only after measured memory telemetry undercuts the conservative band or a GLM-specific implementation is validated.
