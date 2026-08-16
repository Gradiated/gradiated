# Research log

Delegated in Cycle 55 after the exact 39-layer student cleared the measured L40S cost gate. Produce one executable, resource-bounded recovery nomination or close with a typed feasibility result. No provider, GPU, broad evaluation, or holdout access is authorized.

## 2026-07-15 — BF16 recovery preflight and single-job nomination

Question: can the fixed 39-layer student be recovered with a modest route without changing the measured W4 serving mechanism?

Action/evidence: `student39_recovery_preflight.py` read all BF16 safetensors headers without materializing a new checkpoint. It mapped 7,843 retained source tensors / 24,860,902,528 BF16 parameters from layers `0..46` minus `[5,10,15,20,26,31,36,41]` to `0..38` (mapping SHA-256 `e501ab11290cd38424fd5ed93f9e9fd55145a7ed98cb6acddcc21b4122accb3a`), retained norm/head/tokenizer, and excluded MTP. The selected rank-16 LoRA surface is 155 retained attention/router tensors and 11,188,224 trainable parameters. Its deterministic synthetic fixture executed KL plus eight bridge-MSE loss wiring, adapter checkpoint save/reload, and symmetric W4/group-32 packing; all checks passed. This is source-bound and fixture evidence, not a quality result.

Interpretation: a sequential H100/H200-class route is credible: BF16 teacher capture and BF16 student LoRA do not co-reside (72 GiB and 68 GiB admission envelopes respectively); L40S 48GB is excluded. `RECOVERY_JOB_SPEC.json` nominates the sole 4M-token, cache-first FineWeb-Edu job with a 26 GPU-hour / $55.90 actual-reference cap, deterministic source/data manifests, KL/bridge checkpoints at 250k/1M/4M tokens, conversion and frozen-development fail-fast gates. It never trains on the frozen development or holdout records.

Next move: director may schedule only `glm47-student39-bf16-lora-bridge-kl-v1`; otherwise this project is complete at zero provider spend. Quality remains unmeasured until its final development gate.
