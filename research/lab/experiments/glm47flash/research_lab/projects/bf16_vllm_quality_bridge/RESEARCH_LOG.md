# Research log

No researcher result yet. Produce an executable pass/fail bridge under the zero-provider contract in `PROJECT.md`; do not mutate a provider or return a design-only handoff.

## 2026-07-15 — zero-provider BF16/vLLM bridge

Question/action: can the exact complete BF16 checkpoint pass the static vLLM loader, tokenizer, logprob, memory, and V2 artifact gates without provider mutation? Ran the pinned `vllm/vllm-openai@sha256:97187c...` container with Transformers commit `1618d44...`, mounted only the local checkpoint, and executed the project-owned bridge.

Measured/derived evidence: vLLM 0.15.0 imported `vllm.model_executor.models.glm4_moe_lite`; Transformers resolved to `5.3.0.dev0`; the exact config resolved as `glm4_moe_lite`; the exact tokenizer accepted `enable_thinking=False`. vLLM source exposes `prompt_logprobs` on the OpenAI completions path, which is the runtime-produced input-logprob route for a later adapter. The 48-shard manifest matches revision `33faccf4c2ba82142214d0d4e16232a4e9ccfe10`, 62,444,175,504 weight bytes, and SHA-256 `515b8317...`.

The 0.90 allocation envelope is 72 GiB. At the preregistered c1 geometry (9,216 tokens), exact aggregate c1 KV is 498,991,104 bytes (475.875 MiB), leaving 13.379608 GiB after weights plus c1 KV before runtime/workspace reserve. This is a positive analytical memory bound, not a GPU load result. Local `--gpus all` was unavailable because this environment has no NVIDIA driver; no provider or model launch was attempted.

The bridge’s synthetic contract test passes all seven per-capture artifact names, rejects a missing artifact, requires typed terminal/two-view cleanup fields, and rejects the exact V35 read-only `/input` mount pattern. Artifact: `BF16_VLLM_BRIDGE_2026-07-15.json`. Existing 27 launcher tests and bridge byte-compilation pass.

Interpretation: `CONDITIONAL_PASS_STATIC_BRIDGE_GPU_LAUNCH_REQUIRED`. This advances a materially different vLLM route, but does not add quality evidence, prove CUDA graph/workspace reserve, or authorize spend. Next move is one later director-authorized H100 launch; fail closed if model load or three fresh V2 captures cannot retain runtime input logprobs and cleanup.

## 2026-07-15 — quality work deferred for architecture discovery

The user changed the campaign sequence while r3 was in H100 setup: explore telemetry-derived model architecture changes first and defer full quality control until a candidate demonstrates material cost potential. The durable controller was interrupted, the provider resource was absent when independently reconciled, and authenticated final inventories contained zero instances and zero disks. R3 produced no model load, capture, quality result, or scientific evidence. This project is paused and has no provider authority.

## 2026-07-15 — first paid vLLM route terminal before model load

The real `bf16-v2-quality` mode and exact 42,545-token V2 maximum were implemented and tested, then one H100 allocation ran. It reached SSH, CUDA/Transformers preflight, and the transfer probe, but the inherited 900-second model-transfer timeout stopped after 41.298 GB / 32 of 48 shards. No model process, GPU allocation, capture, response, or quality result existed. `artifacts/nebius_h100_bf16_vllm_v2_2026-07-15-r2/summary.json` records 1,648.284 provider seconds, $1.773877104 derived cost, zero manifest files, and verified zero final instances/disks.

The run was launched as an attached researcher child rather than the required durable service. After terminal cleanup, the supervisor independently changed the shared launcher to require its own PID to equal `SYSTEMD_EXEC_PID` before BF16 provider mutation and raised only BF16 transfer timeout to 2,400 seconds; focused and campaign-wide tests plus direct-child rejection and external-service admission proofs passed. These are post-run execution corrections, not quality evidence.

## 2026-07-15 — r4 measured BF16 control and terminal retrieval defect

Question/action: execute the frozen r4 durable H100 session through three resident-checkpoint V2 captures, with no source or readiness edits. The exact frozen launcher/suite/model hashes matched and direct inventories were empty before create.

Measured evidence: the durable `glm47-bf16-vllm-v2-r4.service` reached H100 SSH, CUDA/Transformers preflight, and completed the 48-shard transfer in 1,106.902 s. vLLM loaded the exact BF16 checkpoint with eager c1 and max model length 43,008; captured telemetry reports 77,025 MiB used of 81,559 MiB on the H100 (free 4,055 MiB). All three fresh 36-case captures passed, each retaining the exact seven artifacts, model revision identity, runtime evidence, and prompt-logprob outputs. The retrieved archive is `artifacts/nebius_h100_bf16_vllm_v2_2026-07-15-r4/vllm-awq-batch.tar.gz` with SHA-256 `98e34729b73048ab97e20e66eda4ee807bb6a6e41fbe9c403273135035b39dba`.

Terminal result: the scientific workload passed, but the shared retrieval validator failed closed because BF16’s archive has no legacy `/allocation-result.json` member (`StockError`, typed in `events.jsonl`). The controller still verified cleanup: 1,931.184 s, derived cost `$2.078332603`, zero final instances and disks. This is measured BF16 loader/capture evidence, not a graduation quality claim; the route is terminal until the director separately authorizes a packaging-contract correction.
