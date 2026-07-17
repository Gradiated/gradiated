# Complete-BF16 vLLM quality bridge

## Question

Can the complete V13 BF16 checkpoint and frozen executable V2 development suite run through the proven vLLM lifecycle on one 80-GiB H100, avoiding the failed SGLang adapter while preserving the exact quality artifact contract?

## Why it matters

Quality eligibility is the only unresolved GLM-4.7 graduation gate. The V35 route was scientifically null because its SGLang Docker adapter failed at a read-only bind mount after checkpoint transfer. The current-AWQ L40S path has a proven provider lifecycle and vLLM model support, while retained c16 evidence shows that the old six-case absolute screen fails four categories despite paired non-regression. A distinct complete-BF16 vLLM route can calibrate the prospectively frozen V2 suite without another adapter/controller lineage.

## Relevant evidence

- Complete V13 checkpoint: `/root/.cache/glm47flash-bf16-33faccf4`, revision `33faccf4c2ba82142214d0d4e16232a4e9ccfe10`, 48 shards, 62,444,175,504 weight bytes, manifest SHA-256 `515b831798895e737cfee5943cb522db95cf71d48bb15dfb3f49a016cab9e101`.
- Frozen suite: `projects/quality_gate_calibration/executable_development_v2/MANIFEST.json`, fixture SHA-256 `4953e524526106b353a7df8de6d84e45fa18d96464935117ca926f483d03a6b7`; preregistration SHA-256 `1191fc7643120e8bb1f8eab796fbd22f29e7065b26a1c7b4e28387eddd0b32d8`.
- Proven lifecycle and vLLM quality code: `campaign_100/nebius/vllm_smoke_control.py` and `remote_vllm_awq_smoke.sh`; current vLLM 0.15.0 registers `Glm4MoeLiteForCausalLM` and already retains generation plus runtime prompt-logprob evidence.
- Current authenticated Nebius catalog exposes `gpu-h100-sxm / 1gpu-16vcpu-200gb` with 80 GiB and preemptible support. The complete weights are about 58.15 GiB; verify rather than assume the remaining 90%-allocation envelope is sufficient.

## Scope

Perform one zero-provider, executable admission bridge while the methodology allocation owns provider mutation. Do not create/query-mutate hardware, run a model, access/generate the holdout, edit the frozen suite, patch SGLang, or create a new controller/adapter.

Use the installed pinned vLLM source/container and exact checkpoint/config to prove or falsify the BF16 GLM loader, tokenizer, reasoning-off request policy, runtime-produced input-logprob route, and single-H100 memory admission. Reconcile 90% of 80 GiB against exact resident bytes, source-derived c1 KV at 54,144 bytes/token across 47 layers, alignments, CUDA graph/workspace/runtime reserve, and the V13 measured load footprint where available. Fail closed if the model requires tensor parallelism, unsupported kernels, a different runtime, or less memory headroom than the V2 capture needs.

If admitted, add only a `bf16-v2-quality` scientific mode to the proven vLLM remote script/launcher. It must use a writable script/data path, start the exact BF16 checkpoint on one H100, run three fresh server-process development captures on the resident verified checkpoint, and retain the seven preregistered per-capture artifacts plus typed terminal and two-view cleanup records. Prove the mode locally/fakely end to end, including identity, missing-artifact, timeout, and the exact V35 read-only-mount negative control. Do not build a generic framework or return another design-only document.

This project has $0 authorized spend and no provider ownership. A passing executable bridge earns one later director admission only after the live methodology allocation is terminal and inventories are empty. It does not itself produce quality evidence. A loader, memory, endpoint, or artifact-contract failure closes this vLLM route rather than starting another runtime/controller cycle.

## Available resources

Use the complete local BF16 checkpoint, frozen V2 suite and proofs, current vLLM image/source, the proven Nebius launcher and quality runner, archived V13/V35 manifests and telemetry, and shared factory tools. The shared GPU-price inventory is fresh; do not search prices.

## Portfolio-changing result

A passing executable bridge gives the lab a materially different, bounded path to the sole remaining graduation gate, with no SGLang adapter dependency. A fail-closed result shows that quality cannot be recovered through the proven vLLM lifecycle and supports stopping the GLM-4.7 campaign rather than spending on more controller work.

## Director correction and paid admission — Cycle 32

Reject the claimed executable completion. `bf16_vllm_quality_bridge.py` performs identity arithmetic and writes synthetic filenames, but no `bf16-v2-quality` mode exists in the shared launcher or remote script. Its 13.38-GiB residual also omits the frozen V2 suite's actual maximum token geometry and runtime/CUDA workspace reserve. This is useful static evidence, not a runnable bridge.

Reactivate this same project for one final correction-and-run turn. First tokenize all 36 frozen development fixtures with the exact V13 tokenizer, bind the maximum prompt-plus-output geometry, and admit one H100 only if weights, KV, alignment, and a defensible eager-mode runtime/workspace reserve fit inside the 72-GiB 90% envelope. Add the narrow `bf16-v2-quality` mode to the existing `/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py` and its existing remote script; do not create another Python controller or resurrect the SGLang adapter. Use a writable `/workspace/bf16-v2-quality` path, vLLM eager/c1 settings appropriate for quality rather than throughput, runtime-produced prompt logprobs, and the exact seven-artifact capture contract. Add focused tests that exercise the actual mode and fail on missing artifacts and the V35 read-only mount pattern.

Run an execution-equivalent no-mutation service preflight, then launch the same absolute command in the same researcher turn under a durable user-systemd unit named `glm47-bf16-vllm-v2.service`; no readiness-only return is admissible. The scientific controller and independent instance-plus-disk watchdog must both survive the researcher turn, with absolute paths and observable artifact locations. Use local checkpoint `/root/.cache/glm47flash-bf16-33faccf4`, revision `33faccf4c2ba82142214d0d4e16232a4e9ccfe10`, manifest `515b831798895e737cfee5943cb522db95cf71d48bb15dfb3f49a016cab9e101`, V2 suite manifest `/root/workspace/research/sol/experiments/glm47flash/research_lab/projects/quality_gate_calibration/executable_development_v2/MANIFEST.json`, preregistration `/root/workspace/research/sol/experiments/glm47flash/research_lab/projects/quality_gate_calibration/BF16_DEVELOPMENT_CAPTURE_PREREGISTRATION.json`, pinned vLLM image `sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543`, and the existing matched Nebius SSH key pair.

Grouped mutable checks are empty direct instance/disk inventory, current `gpu-h100-sxm / 1gpu-16vcpu-200gb` orderability, key pairing, exact local files, and the final service command. The first paid gates are exact model identity, CUDA load/memory telemetry, and capture 1; then restart the server process for captures 2 and 3 while retaining the verified checkpoint. Retrieve and validate all raw/logprob/normalized/identity artifacts, freeze the development NLL ceilings, apply the BF16 category gate, and verify two-view cleanup. Holdout, AWQ, and performance work remain prohibited.

Maximum all-in exposure is $4.27, scientific deadline 3,600 seconds, and external service/watchdog deadline 3,900 seconds. Any load, endpoint, artifact, provider, timeout, or cleanup defect closes this vLLM quality route without another admission. A passing BF16 result establishes the control only; the current AWQ economic point remains quality-conditional until a later paired V2 candidate capture.

## Director final durable readmission — Cycle 33

The Cycle 32 run is terminal and cleaned, with $1.773877 derived cost and zero useful GPU seconds. It failed before model load because BF16 inherited the 900-second AWQ transfer timeout, stopping at 41.298 GB / 32 shards; it also ran as an attached researcher child despite the durable-service instruction. Ordinarily the Cycle 32 stop rule would close the route. Make one final portfolio-level exception because the supervisor independently applied and tested both exact fail-before-create corrections after the run: BF16 transfer now has 2,400 seconds, and BF16 provider mutation is rejected unless the launcher's own PID equals `SYSTEMD_EXEC_PID` inside a durable systemd unit.

This is an execution-only readmission. Do not modify the launcher, runner, suite, model, runtime, token geometry, timeout logic, or controller. Re-run the already tested absolute command under `glm47-bf16-vllm-v2.service`, writing to a fresh `projects/bf16_vllm_quality_bridge/artifacts/nebius_h100_bf16_vllm_v2_2026-07-15-r3` directory and using a fresh exact provider name. Before create, group only empty direct instance/disk inventory, H100 orderability, exact local inputs/key pairing, the 42,545-token maximum beneath the bound 43,008 geometry, and proof that the service main PID equals `SYSTEMD_EXEC_PID`. Verify the service and independent instance/disk watchdog are live after create; then allow the durable unit to own transfer, model load, three captures, retrieval, and cleanup through terminal artifacts.

The first scientific evidence remains CUDA model-load/memory telemetry and capture 1, followed by fresh server-process captures 2 and 3. Preserve the exact identities and restrictions from Cycle 32. Additional spend cap is $4.27 and 3,900 seconds; cumulative derived vLLM-route exposure may not exceed $6.043878 including the failed run. Any new provider, transfer, model, endpoint, artifact, timeout, ownership, or cleanup defect closes this quality route and ends further H100 quality work. No other project may mutate a provider while this unit is admitted.

## Director execution-only reactivation — Cycle 55

The prerequisite that paused r3 is now satisfied: the exact 39-layer physical student measured `674.424`, `661.661`, and `734.557` output tok/s at c16/c24/c32, all above the campaign's `594.466`-tok/s economic gate. Resume the frozen BF16 V2 control capture as the sole paid job; this establishes the absolute development category result and freezes the six NLL ceilings needed before a recovered student can make a quality claim.

Run one fresh r4 session under the external systemd unit `glm47-bf16-vllm-v2-r4.service`, provider name `glm47flash-bf16-vllm-v2-r4`, and artifact directory `artifacts/nebius_h100_bf16_vllm_v2_2026-07-15-r4`. The current launcher, remote script, and quality runner hashes are respectively `9428e793515d1a22570b290222f24312970d6f3128c4b814ac24a3f6ccb55599`, `fee4b95fb807c84fc76ed94ae12d175937461ab73389ded18f3611eba8cfecfc`, and `b0222e81147ee19afe837819efac8d3a273df76afec4796aa16e9268bb65d804`. The suite and preregistration hashes remain `d304c6b323cd382b0a952b3389267b8d4881096cb4dc0622b051014769852351` and `1191fc7643120e8bb1f8eab796fbd22f29e7065b26a1c7b4e28387eddd0b32d8`.

This is execution only. Do not edit code, extend timeouts, create a successor controller, substitute preflight/readiness work, access or generate the holdout, or run the student. Use the already tested 2,400-second BF16 transfer allowance and `SYSTEMD_EXEC_PID` ownership guard, then collect the unchanged three fresh server-process captures and exact artifact contract. Maximum additional exposure is `$4.27` and 3,900 seconds including cleanup. A valid BF16 gate result advances candidate recovery; any new operational or scientific failure closes this control route without r5. Always retrieve terminal evidence and verify zero instances and disks.

## Director archive handoff — Cycle 56

r4 completed the scientific capture contract: the exact BF16 model loaded at 77,025 MiB used on the 81,559-MiB H100, and three fresh server processes each returned all 36 frozen cases with the exact seven artifacts. The immutable archive hashes to `98e34729b73048ab97e20e66eda4ee807bb6a6e41fbe9c403273135035b39dba`; the allocation used 1,931.184 seconds, cost `$2.078332603`, and cleaned to zero instances and disks. The terminal `allocation-result.json` error is a legacy outer-validator expectation after capture, not missing scientific rows. Release provider authority and do not run r5. The independent `$0` `bf16_v2_capture_adjudication` project now owns content verification, frozen scorer execution, per-sequence NLL ceilings, and the development-gate decision without changing the archive or accessing the holdout.
