# Research log

Opened by the 2026-07-16 director after the conservative measured-depth transfer parked student42. This project is a single zero-cost exact-W4A16/SM120 admission falsifier, distinct from the closed NVFP4 derivative and generic vLLM release screen. It does not own or observe the live r3 session and may not prepare a provider/controller path.

## 2026-07-16 — terminal GPU_REQUIRED

Question: can one unchanged current published vLLM artifact bind the exact AWQ model's SM120 dense/MoE/MLA/graph paths and c32 memory at zero cost?

Action/evidence: screened published vLLM `v0.25.1`, container `vllm/vllm-openai:v0.25.1-x86_64-cu129-ubuntu2404` (digest retained in the result artifact), and its source tarball. The artifact contains `Glm4MoeLiteForCausalLM`, CUDA 12.0/SM120 build targets, compressed-tensors WNA16 dense Marlin selection, and compressed-tensors WNA16 Marlin MoE selection. The exact checkpoint identity remains config `079f8f…`, index `b9c534…`, manifest `e201ed…`; the source-bound model geometry is 47 layers, 64 experts, top-4 routing, and MLA ranks 512/768. Analytical c32 projection is `46,875.7 MiB`; 96 GiB with a 20% reserve leaves `78,643.2 MiB`, or `31,767.5 MiB` above that projection.

Interpretation: exact MLA backend dispatch, CUDA graph capture, and absence of generic/dequantized/eager fallback are device/runtime observations, not source-string claims. This host has no vLLM/CUDA/GPU, and scope forbids provider access, live capacity queries, and spend. The unchanged-artifact test therefore hit an unavoidable device boundary before the technical pass; rate binding was correctly not reached.

Decision: `GPU_REQUIRED`, terminal for this project. No provider/controller or successor preflight was created. See `artifacts/SM120_AWQ_ADMISSION_SCREEN_2026-07-16.json`.
