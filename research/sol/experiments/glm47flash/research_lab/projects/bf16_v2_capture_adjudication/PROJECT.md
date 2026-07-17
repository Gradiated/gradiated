# BF16 V2 capture adjudication

## Question

Do the three completed r4 BF16 captures pass the prospectively frozen 36-case development gate, and what exact per-sequence NLL ceilings do they establish for a recovered 39-layer candidate?

## Why it matters

The H100 scientific workload is already complete and paid for. The immutable archive contains three fresh server-process captures, 36 cases each, with all seven preregistered artifacts, exact BF16 revision `33faccf4c2ba82142214d0d4e16232a4e9ccfe10`, runtime prompt logprobs, and verified cleanup. The outer controller failed only because a legacy retrieval validator expected `/allocation-result.json`, which was never part of the V2 per-capture contract. Rerunning H100 would add cost without new model evidence; the missing decision is deterministic local scoring.

## Fixed inputs

- Archive: `../bf16_vllm_quality_bridge/artifacts/nebius_h100_bf16_vllm_v2_2026-07-15-r4/vllm-awq-batch.tar.gz`, SHA-256 `98e34729b73048ab97e20e66eda4ee807bb6a6e41fbe9c403273135035b39dba`.
- Frozen suite: `../quality_gate_calibration/executable_development_v2/development.jsonl`, fixture SHA-256 `4953e524526106b353a7df8de6d84e45fa18d96464935117ca926f483d03a6b7`, manifest SHA-256 `d304c6b323cd382b0a952b3389267b8d4881096cb4dc0622b051014769852351`.
- Frozen preregistration: `../quality_gate_calibration/BF16_DEVELOPMENT_CAPTURE_PREREGISTRATION.json`, SHA-256 `1191fc7643120e8bb1f8eab796fbd22f29e7065b26a1c7b4e28387eddd0b32d8`.
- Gate: at least 5/6 point score in every category. For each of six teacher-forced sequences, freeze the candidate ceiling to `1.05 * max(mean control NLL across captures)`.
- r4 allocation evidence: 1,931.184 seconds, `$2.078332603`, 77,025 MiB loaded GPU memory, archive/capture contract complete, zero final instances and disks.

## Scope

Work only from immutable local inputs at `$0`. Verify the archive, internal manifest, identities, case sets, required artifacts, token-sequence hashes, and raw-response hashes independently before scoring. Implement the smallest deterministic scorer needed by the frozen suite: canonical JSON equality for tool and serving cases; exact normalization for retrieval and continuation; one accepted bare-Python or single-`python`-fence extraction followed by the frozen tests in a resource-limited subprocess; and teacher-forced mean NLL from finite runtime input-token logprobs with the minimum scored-token and sequence-hash rules. Do not invent tolerances, repair outputs, change prompts, or transfer results across missing identities.

Score every capture separately, report category totals and repeatability, then freeze all six NLL ceilings exactly as preregistered. Classify the missing legacy `allocation-result.json` separately from the scientific development result. Do not edit the archive, launcher, suite, or prior project; do not access/generate the holdout, call a model, allocate a provider, or reinterpret the gate after observing scores.

## Portfolio decision

If archive integrity and all scorer contracts pass and every BF16 category reaches 5/6, establish the BF16 development control and unlock only a bounded student recovery canary; the recovered candidate must later run the identical frozen evaluator. If any identity/evidence rule fails or any category misses, close the current quality gate and do not fund recovery against it until a new campaign-level quality decision is made. A BF16 development pass is not candidate quality, holdout quality, or graduation.

## Artifact contract

Produce `adjudicate_bf16_v2_capture.py`, `BF16_V2_CONTROL_ADJUDICATION.json`, `BF16_V2_NLL_CEILINGS.json` only on a valid control adjudication, focused tests/negative controls, and a concise `RESEARCH_LOG.md`.

## Available resources

Use the lab archive, frozen suite, prior quality proofs, and shared repository tools. No provider, GPU, network search, or price work is authorized.
