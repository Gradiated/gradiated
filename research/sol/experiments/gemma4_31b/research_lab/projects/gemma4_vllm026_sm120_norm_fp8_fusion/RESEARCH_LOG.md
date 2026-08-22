# Research log

## 2026-07-29T06:48:29Z — concrete offline fusion candidate

- Question: bind and implement one exact official-vLLM 0.26.0 Gemma 4 norm-to-online-FP8 boundary without using the reserved RTX bench.
- Action: traced `Gemma4DecoderLayer.input_layernorm` into `self_attn.qkv_proj`, extended the existing `QuantizedActivation` contract to dynamic per-token FP8 for CUTLASS, exposed that contract from `Fp8PerTensorOnlineLinearMethod`, and routed the Gemma boundary through the shipped `rms_norm_dynamic_per_token_quant` CUDA op with stock fallback.
- Evidence: the patch applies cleanly to official tag `v0.26.0` commit `568afb3a13806beb53bb2e6bd518269357b237c0`; all five upstream source hashes match; patched files compile as Python; `ops.cutlass_scaled_mm` is unchanged. See `artifacts/OFFLINE_VALIDATION.json`.
- Interpretation: this is a concrete semantics-preserving production path, not typed `none`. At c32 decode it predicts one launch and 688,128 BF16 bytes removed per layer boundary, or 60 launches and 41,287,680 bytes per 60-layer batched decode step.
- Next: after an explicit director handoff, run `sm120_framework_oracle.py` on the exact vLLM 0.26.0+cu129/Torch 2.11.0+cu130 sm_120 runtime, then promote a positive component result to the c32 endpoint.

## 2026-07-29T07:16:00Z — lifecycle-pure component owner prepared

- Action: added `run_sm120_norm_fp8_component_owner.py` and validated it offline. It binds the admitted result, preparation packet, patch, oracle, wheel, and future execution binding before starting a same-claim heartbeat; it preserves the loaded endpoint and runs the exact seven-row framework oracle through the resident runtime only after an explicit future claim.
- Evidence: `artifacts/COMPONENT_OWNER_OFFLINE_VALIDATION.json` passed. Owner `b8a43064…`, oracle `49cf6420…`, and patch `79b97e9d…` are recorded in `VLLM026_SM120_NORM_FP8_COMPONENT_OWNER_OFFLINE_RESULT.json` with its controller-host `detached-owner --unit-manager pid` command.
- Interpretation: this is execution preparation only: zero GPU/pool/SSH/provider calls, zero spend, and no scientific sample. Incomplete ordinary integration failures retain the live claim through the shared repair handshake; correct non-positive component evidence releases to maintenance and a positive result retains the claim for director endpoint integration.
- Next: the $3 reservation is now durable; wait only for the later director execution binding. No pre-binding claim is authorized.

## 2026-07-29T07:18:00Z — atomic claim owner repair

- Question: make the prepared controller runnable without a director guessing the pool claim-generation timestamp.
- Action: moved the exact `gpu_pool claim --bench` into the owner before heartbeat and remote execution, derived `claimed_at` solely from the returned claim object, and passed that exact generation to every repair ID and maintenance release. The pre-claim field is now the absolute `claim_start_by_utc` fence.
- Evidence: `validate_component_owner.py` dynamically fakes the pool response and proves the returned `claimed_at` reaches `--expected-claimed-at`; its control-flow assertion proves claim precedes the heartbeat thread and remote call. Validation passed with owner `1493d1e6…`.
- Interpretation: this corrects lifecycle ownership without a GPU, SSH, or provider call. The seven-row one-submission oracle, patch, resident endpoint preservation, and `framework_oracle_only` repair scope remain unchanged.
- Next: a later director binding may authorize the atomic claim; the bench stays untouched until then.

## 2026-07-29T07:25:00Z — remote stage and terminal ownership repair

- Action: post-claim staging now writes the hash-bound patch and oracle atomically into a fresh per-generation component root. The component process copies the installed vLLM package to a disposable overlay, verifies the four admitted base Python source hashes, patches only that overlay, and removes it on exit.
- Evidence: the expanded validator passed owner `70458b97…`; it proves staging precedes the consumer, a complete positive or non-positive terminal reaches generation-fenced maintenance release, and incomplete outcomes reach the live `framework_oracle_only` repair handshake first.
- Interpretation: no source checkout, endpoint restart, or mutable endpoint-package edit is assumed. The owner preserves the atomic claim path, seven-row one-submission contract, patch, oracle, checkpoint, and endpoint.
- Next: wait for a later director execution binding; the maintenance bench remains unclaimed.

## 2026-07-29T08:09:01Z — same-claim installed-source repair launched

- Action: replaced only predecessor owner PID `3990817`/start ticks `142664358` after a final exact-generation census found the original claim intact, no science/result marker, and no remote oracle driver. The replacement uses fresh repair generation `sm120-norm-fp8-installed-source-20260729T0756Z`, owner `f82f41ad…`, and installed-overlay transformer `251aede8…` under the original `07:33:28Z` claim.
- Evidence: the transformer applied to a disposable copy of the actual resident official vLLM package before replacement without CUDA or requests; offline lifecycle validation passed. Replacement PID `4008130`/start ticks `142855921` is durable and its remote root contains only staged inputs and a disposable package overlay at this snapshot.
- Interpretation: the prior two hunk rejects are an ordinary source-context defect, not a consumed component sample. The live endpoint and checkpoint are untouched; the seven-row oracle remains the only permitted submission.
- Next: let this owner complete the framework oracle or retain the same claim through its `framework_oracle_only` repair handshake; no competing owner or endpoint replay is allowed.
