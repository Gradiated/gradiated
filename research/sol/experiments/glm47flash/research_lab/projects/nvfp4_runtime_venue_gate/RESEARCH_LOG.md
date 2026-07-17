# Research log

## 2026-07-15 — GPU-free runtime/venue gate

- Question: can the exact `unsloth/GLM-4.7-Flash-NVFP4@98b0362133bda9ee3b1b875636636c07861f5947` earn a later Blackwell measurement?
- Action: fetched only HF metadata/config/index/recipe/tokenizer metadata (no weights), parsed the 35,688-entry manifest, and audited vLLM main at commit `66b6c684ab5a32dabcd2e69daaa60ff5d5198392`.
- Evidence: architecture registry maps `Glm4MoeLiteForCausalLM`; MTP registry maps `Glm4MoeLiteMTP`; 212 manifest entries belong to `model_mtp.safetensors` and correspond to layer 47 with `num_nextn_predict_layers=1`; the mixed compressed-tensors schema matches the source `CompressedTensorsW4A4Nvfp4MoEMethod` (group-16 NVFP4 MoE, FP8 scales). Official vLLM documentation sets NVFP4 at SM100/Blackwell. Raw hashes and details are in [NVFP4_GATE_2026-07-15.json](./NVFP4_GATE_2026-07-15.json).
- Venue/economics: RunPod lists RTX Pro 6000 Blackwell 96 GB at `$1.99/h` and B200 180 GB at `$5.89/h`; Google Cloud lists RTX PRO 6000 96 GB at `$1.09565/h`. With a deliberately optimistic 15% all-in lifecycle allowance, the target gate requires respectively `998.734`, `2956.053`, and `549.881` sustained output tok/s, versus the campaign control `355.772` tok/s. Catalog listings do not prove current capacity.
- Interpretation: runtime/source compatibility is a conditional pass, but no executable load, quality evidence, live capacity, or plausible conservative break-even exists. The RTX Pro hypothesis is the least implausible but still needs a fresh quality-preserving throughput result at 1.55× control before it can clear the target. Do not spend or promote this lineage in the current campaign.
- Next move: close this project as a useful negative gate; only reopen after someone supplies an accessible Blackwell placement and a frozen quality route, then run one exact load before throughput.
