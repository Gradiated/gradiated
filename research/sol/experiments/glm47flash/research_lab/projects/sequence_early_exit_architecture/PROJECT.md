# Sequence-level early-exit architecture

## Question

Can GLM-4.7 Flash switch a useful fraction of background-agent sequences from full-depth decoding to a late intermediate exit head and reduce sustainable L40S c16 cost by at least 10%?

## Why it matters

Fixed removal of five blocks barely reached a 10.42% optimistic summed-work ceiling and had no recovery evidence. Sequence-level early exit is a different architecture: retain full-depth prefill and initial decoding, then move an entire sequence to a shallower recurrent path after a confidence decision. This avoids creating missing tail-layer KV for tokens that later return to full depth, and concentrates semantics change on requests/tokens that a learned head judges safe. The campaign explicitly permits an early-exit head and modest distillation after the cost mechanism is established.

## Scope

At zero provider spend, use the exact stock serving graph—47 transformer layers, dense layer 0 plus MoE layers 1–46—and treat checkpoint layer 47 as the separate configured MTP payload rather than serving depth. Bind the c16 8,192-input/1,024-output workload, retained decode traces, corrected per-block weight/KV accounting, and pinned vLLM source. Screen only a few late exits, such as after serving layers 35, 39, or 43. The mechanism must perform full-depth prefill and define a one-way per-sequence handoff; after handoff, all future tokens use the selected intermediate hidden state and an auxiliary or reused vocabulary head. Do not model tokenwise exit followed by re-entry, because that would omit tail-layer KV state.

Derive the minimum fraction of output tokens and sequences that must use each exit to reach the committed-price target, accounting separately for unchanged prefill, vocabulary projection, saved tail-block work, switching/head overhead, and c16 background completion. Calibrate against the measured 535.286 output tok/s control and the poor prior transfer from summed kernel work; do not treat proportional block count as endpoint wall time. Report weight/KV residency and whether a late head changes c32 or cheaper-placement admission.

Build the smallest source-bound executable proxy or fail-closed fixture that proves the one-way sequence state transition, selected-layer hidden shape, head invocation, request completion, and stock mode inside the pinned runtime. Synthetic/oracle exit decisions are allowed and explicitly change semantics. Do not train, run a provider, evaluate broad quality, change MoE routing, skip fixed blocks for all sequences, alter MLA/precision, or build a scheduler framework. State the minimal later L40S experiment and the confidence/acceptance counters needed if a candidate survives.

## Resources

- Current control: 535.286 output tok/s and about `$0.571/M` at the fresh `$1.10/L40S-hour` planning rate.
- Depth evidence: `../layer_depth_architecture/depth_bound.json` and `depth_proxy.py`; correct its checkpoint-header layer-47 count to the stock 47-layer serving graph above.
- Current AWQ checkpoint: `/root/.cache/glm47flash-awq-ab31d120`.
- Output-head evidence: `../output_head_architecture/`.
- L40S dossier: `../../hardware/L40S.md`.
- Runtime and retained traces: `/root/workspace/research/sol/experiments/glm47flash/campaign_100`.

## Portfolio-changing result

Nominate at most one late exit only if exact accounting, a source-bound executable proxy, and explicit switch-rate/overhead thresholds support a conservative path to at least 10% lower c16 cost or a real placement discontinuity with plausible modest distillation. Otherwise close early exit without provider work. This project has no provider authority or spend.

## Director continuation — Cycle 48

Reactivate this project for one zero-provider runtime-feasibility falsifier, not for a new analytical early-exit survey. Bind the exact derived runtime `glm-vllm:0.15.0-transformers-1618d44`, its GLM model-forward source hash, and the current scheduler geometry. Implement the smallest content-bound local patch/fixture that runs all 47 serving layers for prefill and layers 0–34 only for decode, then applies the stock final norm and reused vocabulary head. The all-sequence forced exit is an architecture-cost ceiling and intentionally changes semantics; it is not the eventual 50% confidence policy.

Prove or falsify phase detection through actual pinned forward metadata, full tail-KV creation during prefill, absence of tail-layer decode/KV writes, stable hidden and logits shapes, stock-mode identity, deterministic rejection of mixed prefill/decode batches if they cannot be handled safely, Python compilation, and a local source-bound call trace. Do not modify the shared launcher, allocate CUDA, mutate a provider, train a head/gate, or build selective per-sequence scheduling. If phase-aware layer stopping requires a scheduler rewrite, attention-metadata slicing, or a new engine, close this candidate rather than preparing that infrastructure.

If the exact runtime path passes, preregister only one later L40S stock-c16 versus forced-all-exit-35 cost-ceiling session after the active W4-head allocation reaches terminal cleanup. That future arm must preserve full-depth prefill, report prefill/decode timing separately, and show enough measured all-exit reduction that a derived 50% switch policy with 2% decode-equivalent overhead can still reach 594.466 output tok/s; the current analytical all-exit reference is 669.459 tok/s. Passing the ceiling would justify later confidence/recovery work, not a deployable-quality claim.

## Director continuation — Cycle 49

The local phase contract passed and the W4-head allocation is terminal with authenticated zero-instance/zero-disk cleanup. This project is now the sole paid provider owner for one matched L40S ceiling session, capped at `$1.15` and 4,500 allocation-seconds. Use the proven shared launcher `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py`, the exact local checkpoint `/root/.cache/glm47flash-awq-ab31d120`, base image `vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543`, and derived runtime `glm-vllm:0.15.0-transformers-1618d44`. One external systemd process whose `SYSTEMD_EXEC_PID` equals the launcher PID must own create, adjacent arms, retrieval, spend accounting, and cleanup; preserve the absolute cleanup watchdog and exact-name inventory reconciliation. Do not create a project-local provider controller.

On one allocation, run stock c16 and forced-all-exit-35 c16 adjacently with identical 8,192-input/1,024-output requests, `max_num_seqs=16`, `num_kv_splits=4`, cache-off accounting, and the campaign's background completion envelope. The arm must execute all 47 layers for prefill, only layers 0–34 for decode, and then the stock final norm and vocabulary head. Require full request completion, stock-mode identity, stable request/logit semantics diagnostics, no tail-layer decode calls or tail-KV writes, prefill/decode timing, peak VRAM, useful GPU seconds, server/GPU telemetry, exact spend, archive retrieval, and zero-resource cleanup. Candidate outputs may differ because this is deliberately semantics-changing; the diagnostics must prove a coherent execution, not quality equivalence.

The direct ceiling passes only at `>=594.466` output tok/s. Continue later toward a selective policy only if measured phase decomposition supports a 50% switch policy plus 2% decode-equivalent overhead at `>=594.466` output tok/s; otherwise close early exit. Allow one material in-place correction inside the same allocation. Another failure before scientific execution closes this execution route. Do not train a gate/head, run broad quality, add mixed-phase scheduler machinery, or make a production claim.

## Director continuation — Cycle 50

The exact source-bound patch now exists and compiles against expected vLLM source SHA-256 `6a984f701d46dfa05389a45d7aedde6a10ef45a6f59e73d3bbfa1e82f556b4a9`; no provider spend occurred. This is the final integration-to-measurement continuation, not another local feasibility turn. Edit the named shared launcher and remote arm path directly so the immutable manifest stages `exit35_vllm_source_patch.py`, verifies that source hash before applying it, and sets `VLLM_EXIT35_MODE=1` only for the candidate server. Preserve the adjacent stock arm and all Cycle 49 workload, ownership, telemetry, spend, and cleanup requirements.

Run focused launcher tests and the execution-equivalent no-mutation terminal, then immediately start the externally systemd-owned matched session in the same return. Do not add another project-local patch, controller, staging plan, or readiness artifact as the terminal result. A concrete shared-integration/runtime blocker or a second pre-science failure closes this paid route and releases provider authority; otherwise return the measured stock/exit ceiling. The `$1.15` and 4,500-second cap is unchanged.
