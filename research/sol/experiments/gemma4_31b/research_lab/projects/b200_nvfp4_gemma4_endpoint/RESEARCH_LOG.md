# Research log

## 2026-07-28 — native endpoint packet

Question: can the exact Gemma 4 revision use the predecessor's native W4A4
NVFP4 path in a complete B200 c32 endpoint rather than only in isolated
linears?

Action: consumed predecessor terminal `0838a226…`, read the pinned
compressed-tensors dispatch contract, and implemented the immutable packet at
`artifacts/native-nvfp4-endpoint-packet-v1`. It binds the 62,578,655,208-byte
eight-file checkpoint, tokenizer/template hashes, pinned image/commit, c32
4214/358 workload, conservative 300-GiB disk / 90-minute owner request, and
same-session B200 BF16 control. The worker atomically copies verified bytes
under its project root before conversion, verifies the W4A4 symmetric-float4
group-16 contract, and launches the pinned runtime with compressed-tensors.

Evidence: `PACKET_MANIFEST.json` SHA-256
`707b20f442ade965a9970d3338d8b608946cf4e3168fa7257111963b38f0b116`;
Python compilation and shell syntax passed. The exact vLLM source semantics
require NVFP4 weights and input activations both to be float4 group-16, which
selects `CompressedTensorsW4A4Fp4`; this supports implementation, not an
endpoint result.

Interpretation: the inventory contains a cold B200 reservation but its state
is `maintenance` and expressly non-claimable pending director verification.
No provider API, SSH, claim, CUDA call, conversion, server, or scientific
sample was made. Actual project spend remains `$0.00`.

Next: after the director marks the listed B200 ready, launch one durable
shared-tool owner; run BF16 control then native-NVFP4 candidate, retaining the
claim for ordinary launcher/consumer repair and measuring complete requests.
