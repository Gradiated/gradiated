# Current-AWQ SM120 admission screen

## Question

Can one published current vLLM runtime execute the exact current GLM-4.7-Flash compressed-tensors W4A16 checkpoint on an RTX PRO 6000 Blackwell Server Edition (`sm_120`, 96 GB) without unsupported binaries, source patches/builds, eager-only operation, or silent dense/MoE kernel fallback, and does one current content-bound rate make a later exact-load measurement economically worth considering?

## Why it matters

Student42 is now parked: its measured-transfer lower bound is `568.750` output tok/s, below the `594.466` economic gate. The active full-model L40S FP8 session tests representation, but the same exact W4A16 model on a 96-GB Blackwell workstation/server GPU is a materially different placement mechanism: c32 BF16-KV should fit without changing weights or KV precision, while the shared inventory reports 188 SMs and 1,597 GB/s GDDR7 versus L40S's 142 SMs and 864 GB/s. This avoids transferring the closed NVFP4 derivative's quality and format assumptions. The missing facts are exact SM120 runtime dispatch and sustainable rate, not another model manifest or broad hardware survey.

## Fixed evidence

- Model root `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, manifest SHA-256 `e201edca069d0cfd91c81a7407e40a1b09808448704b2fc8c31e99ff6d9d0a86`, 4 shards / `20,170,199,928` weight bytes / 28,221 index entries.
- Exact architecture `Glm4MoeLiteForCausalLM`; compressed-tensors `pack-quantized`, 4-bit, group-32, symmetric W4A16 representation; BF16 activations and residuals.
- Workload: cache off, 8,192 input / 1,024 output, `num_kv_splits=4`, background c32 primary, complete requests within 300 seconds.
- Measured L40S full-model c16: `535.2861037029285` output tok/s and 44,103 MiB peak. L40S c32 projects to 46,875.7 MiB; the 96-GB candidate removes that capacity discontinuity without requiring FP8 KV.
- Economics: `$0.514/M` output tokens. For any all-in hourly rate `R`, required sustained throughput is `R * 1,000,000 / (3,600 * 0.514)`.
- Consume, do not repeat:
  - `../vllm_release_delta_screen/artifacts/VLLM_RELEASE_DELTA_SCREEN_2026-07-15.json`, which establishes v0.25.1 config-level WNA16 selection but not SM120 backend/no-fallback execution;
  - `../nvfp4_runtime_venue_gate/NVFP4_GATE_2026-07-15.json`, which covers a different W4A4 NVFP4 checkpoint and only historical venue leads; and
  - `/root/workspace/research/factory/data/accelerator_inventory.json`, current for the RTX PRO 6000 Blackwell Server geometry. The fresh shared price inventory has no entry for this accelerator.

## Scope

Run one bounded `$0` admission falsifier. Pin exactly one published current stable vLLM release and one reproducible published wheel/container artifact. Inspect or execute its CPU/config/platform selection only as needed to bind:

1. `Glm4MoeLiteForCausalLM` architecture and WNA16 compressed-tensors selection;
2. explicit `sm_120` build coverage and CUDA/toolchain compatibility for the published artifact;
3. dense Marlin/WNA16 linear, compressed-tensors Marlin MoE, MLA/attention, BF16 activation/residual, and CUDA-graph paths used by this exact model;
4. absence of silent generic, dequantized, eager-only, unsupported-binary, source-patch, or source-build fallback; and
5. exact c32 memory admission on 96 GB with a conservative runtime/graph/allocator reserve.

Use model metadata and source-bound exact shapes; do not load or copy weight payloads. A small platform/config probe is permitted only if it exercises the published artifact unchanged and records the selected backend. Source-string presence alone is not a pass.

Only if the technical path passes, perform one targeted current rate check for the exact RTX PRO 6000 Blackwell **Server Edition** or an execution-equivalent 96-GB `sm_120` topology. This is the missing-accelerator exception to the fresh shared price inventory, not a broad GPU-price refresh. Bind accelerator, topology, region, capacity type, included host/storage/network components, billing minimum, and retrieval time. A virtual-workstation label, stale catalog number, or GPU-only rate remains a lead, not an all-in planning rate. Do not query live capacity or use credentials.

For a technically passing, rate-bound candidate, derive the required tok/s at the exact rate and compare it with conservative L40S-to-SM120 resource envelopes without claiming transferred throughput. Nominate at most one later exact-load/c16-c32 measurement only if the rate and physical envelope leave a credible path to `$0.514/M`; otherwise close or return `PRICE_UNBOUND`.

Do not access or observe the active r3 session, query/mutate a provider, use CUDA, edit a launcher/checkpoint/runtime, download weights, run inference, train, evaluate quality, repeat NVFP4 metadata, perform a broad release diff, or create controller work.

## Budget, decision, and stop rule

Maximum wall time is 600 seconds, peak RSS 4 GiB, new artifacts 32 MiB, and provider spend zero. One attempt, one terminal result, no successor preflight.

- `NOMINATE_EXACT_LOAD`: every exact runtime/backend/memory gate passes in an unchanged published artifact, one content-bound all-in rate is current, and its required throughput has a credible physical path.
- `TECHNICAL_CLOSE`: any exact SM120 binary, WNA16 dense/MoE, MLA/attention, graph, or no-fallback gate fails or requires a patch/source build/eager-only mode.
- `PRICE_UNBOUND`: the technical path passes but no exact content-bound sustainable rate supports a decision.
- `GPU_REQUIRED`: the bounded unchanged-artifact test cannot cross an unavoidable device boundary. This is terminal and does not authorize another preflight.

## Artifact contract

Produce one compact JSON binding runtime and artifact identities, exact model/config/index hashes, component-by-component backend selections, SM120 build/toolchain evidence, fallback checks, c32 memory accounting, targeted rate evidence if reached, required-throughput formula/result, physical-envelope interpretation, and typed decision; add only a concise `RESEARCH_LOG.md` update and focused project-local probe if required.
