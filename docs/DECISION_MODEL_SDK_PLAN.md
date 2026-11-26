# `grad` — Model Training, Serving & Trajectory Sync Platform: Server, Artifact, CLI, and SDK Contracts

Status: **Draft v14 — Blueprint Locked** *(5 irreducible primitives; validated against 140+ post-training methods and 60 executable PyTorch implementations with bit-exact `0.00e+00` surrogate-gradient verification — ready to scaffold `Gradiated/grad`)*.

This document defines the contracts for **`Gradiated/grad`**: an open-source (initially private, Apache-2.0 / MIT ready for public release) **general model training, serving, and trajectory-sync platform** that:
1. Trains **any task-specific model type** from production traces, structured datasets, or live stateful environments (Docker Compose stacks, sandboxes, MCP tools) — without hardcoding router-only schemas (e.g. LLM model routers, effort-level detectors, classifiers, reward models, Cartridges, and generative fine-tuned/RL models like diff-merge).
2. Runs identically **locally via `docker compose`** (CPU default + optional `--profile gpu`) and **hosted in Gradiated Cloud**.
3. Uses a **thin Rust server** (`server/api` + `server/runtime`) for inference dispatch, pluggable runtimes, online SLA/canary serving, and job orchestration, paired with a **Python training/eval/sync worker** (`server/trainer`, CPU or GPU) compiling models into immutable `.grad` artifacts.
4. Exposes one **OpenAPI 3.1 contract** with high-quality open-source-generated **v0 SDKs in TypeScript, Python, Go, and Rust**, plus a lightweight **Rust `grad` client CLI**.
5. Integrates bidirectionally with all major LLM observability providers (PostHog, Langfuse, Braintrust, LangSmith, Phoenix, Datadog, Weave, Opik, Logfire, Laminar, Helicone, OTEL).

Related Gradiated contracts:
- [docs/TRACES_PLAN.md](TRACES_PLAN.md) — `GenerationContent` (`gradiated.generation-content/1`), relay/hosted capture, and S3 batch layout.
- [docs/TASK_FINE_TUNING_GATEWAY_CONTRACT.md](TASK_FINE_TUNING_GATEWAY_CONTRACT.md) — Rust gateway credentialing, model resolution, headers, and bounded capture.
- [docs/TASK_FINE_TUNING_RUN_CONTRACT.md](TASK_FINE_TUNING_RUN_CONTRACT.md) — Temporal workflow orchestration, PostgreSQL run state, and S3 artifacts.
- [docs/TASK_FINE_TUNING_EVALUATION_CONTRACT.md](TASK_FINE_TUNING_EVALUATION_CONTRACT.md) — Frozen holdouts, deterministic judge protocol, and ClickHouse run events.
- [docs/CARTRIDGE_SERVING_PLAN.md](CARTRIDGE_SERVING_PLAN.md) — Compressed KV-cache Cartridge serving.

---

## 1. The 5 Irreducible Primitives

Every concept in `grad` maps to one clear, non-overlapping noun:

| # | Primitive | Strictly 1 or Many? | One-Sentence Mental Model | Core Operations |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **`Trajectory`** *(in a **`Dataset`**)* | Data | Universal model-agnostic data unit covering production traces (PostHog/Langfuse/Braintrust/Gradiated), supervised `(input → expected_output)`, multimodal `media[]`, and multi-turn RL rollouts (w/ atomic `.append_env_tokens()` and `.to_datum()`). | `import`, `sync`, `split`, `append_env_tokens()`, `to_datum()` *(custom loops)* |
| **2** | **`Environment` + `Rubric`** | Task & Scoring | Optional stateful harness (Docker Compose stacks, seed scripts, MCP tools, sandboxes, counterfactual replay) with explicit `setup / step / evaluate(handle, traj) / teardown` lifecycle + composable scoring (pointwise `RewardFunc`, groupwise comparative rubrics, `ExistingScoreReward`). | `setup()`, `step()`, `evaluate()`, `teardown()`, `rollout_groups()` |
| **3** | **`Trainer`** *(composed by **`Recipe`** / **`Pipeline`**)* | Weight Mutation | Remote engine that learns weights (metered per million tokens processed + weight storage) — either via composable `Recipe` / `Pipeline` runs (`RouterRecipe`, `ClassifierRecipe`, `SFTRecipe`, `DPORecipe`, `GRPORecipe`, `DistillRecipe`, `CartridgeRecipe`) or interactive custom training loops (`fit_batch`, `forward_backward` accepting both built-in `Loss` and `CustomLoss` subclasses over `forward`+`backward_surrogate`, `optim_step`, `save_state`, `trainers.resume`, `snapshot()`, `export()`). | `runs.create()`, `fit_batch()`, `forward_backward()`, `optim_step()`, `snapshot()`, `export()` |
| **4** | **`Artifact(Model)`** *(a `.grad` bundle)* | **ALWAYS 1 immutable model** | Subclasses `Model` (`Model("Qwen/Qwen3-32B")` pure ref or `client.models.get(...)` live handle). One concrete, versioned, callable model (`support-router@2026-11-25-1` or ephemeral `trainer.snapshot()`). Owns weights + tokenizer + runtime hooks (steering/grammar) + offline `EvalReport` + lineage + `.deploy()`. | `infer()`, `infer_batch()`, `sample()`, `score_logprobs()`, `embed()`, `tokenize()`, `deploy()`, `merge()` |
| **5** | **`Endpoint`** *(live production slot)* | **1 OR MANY `Artifact`s** | Named production serving alias (`POST /v1/endpoints/{name}/infer` + `POST /v1/feedback`). Owns traffic splits (`active`, `canary`, `shadow`), online safety/calibration (`SLAPolicy`, confidence/syntax fallbacks), multi-model / test-time strategies (`Cascade`, `BestOfN`, `MajorityVote`, `BudgetForcing`), and automatic `Trajectory` logging. | `infer()`, `feedback()`, `promote()`, `canary()`, `shadow()`, `status()` |

> **30-second mental model:** Import or sync **`Trajectories`** into a **`Dataset`**. Define a **`Rubric`** (and optional stateful **`Environment`**). Run a **`Recipe`** on a **`Trainer`** to produce an immutable **`Artifact`**. Shadow, canary, or promote 1 or more **`Artifact`s** onto a live **`Endpoint`**, call `endpoint.infer()` + `endpoint.feedback()`, and live **`Trajectories`** flow right back in for the next train.

---

## 2. Repository & System Topology (`Gradiated/grad`)

### 2.1 Repo Layout

```text
Gradiated/grad/
├── Cargo.toml                    # Rust workspace: server/api, server/runtime, cli, sdks/rust
├── spec/
│   └── openapi.yaml              # Single source of truth (OpenAPI 3.1, validated from Rust via utoipa)
├── server/                       # Open-source server (local Docker Compose, Helm chart, + Gradiated Cloud)
│   ├── docker-compose.yml        # 1-command local stack (CPU default; `--profile gpu` for CUDA trainer/serving)
│   ├── helm/grad/                # Official Helm chart (`charts.gradiated.com`) for production Kubernetes (CPU + GPU node pools)
│   ├── api/                      # Rust (Axum): OpenAPI HTTP server, auth, DB state, job/session proxy, OTLP sink
│   ├── runtime/                  # Rust crate (`grad-runtime`): pluggable runtime adapters
│   │   ├── onnx_runner.rs        #   in-process `ort` ONNX (routers, effort detectors, classifiers, GBDTs)
│   │   ├── endpoint_policy.rs    #   canary/shadow, Valkey online LCB/IPS SLA, cascade/voting orchestration
│   │   └── remote_llm.rs         #   forwards generative/LoRA/Cartridge artifacts to vLLM/SGLang/Gradiated GPU runtime
│   └── trainer/                  # Python worker (CPU default / GPU pool): primitives, recipes, trace parsers/sync
│       ├── core/                 #   Trajectory, Datum, Environment, Rubric, ModelSpec, Trainer, Artifact I/O
│       ├── recipes/              #   readable OSS recipes (router_dual_head, effort_ordinal, diff_merge_sft/grpo, opd, dpo)
│       └── connectors/           #   inbound Parquet/JSONL parsers & provider sync APIs
├── cli/                          # Rust `grad` client CLI (single static binary via cargo-dist / Homebrew)
├── sdks/
│   ├── typescript/               # `@gradiated/grad` (npm) — @hey-api/openapi-ts + ~200 LOC idiomatic façade
│   ├── python/                   # `grad-sdk` (PyPI) — openapi-python-client + ~200 LOC idiomatic façade
│   ├── go/                       # `github.com/Gradiated/grad/sdks/go` — oapi-codegen + idiomatic façade
│   └── rust/                     # `grad-sdk` (crates.io) — progenitor + idiomatic façade
├── scripts/
│   └── generate-sdks.sh          # Deterministic CI regeneration + shared wire-level contract tests across all 4 SDKs
└── examples/                     # Router, effort detector, diff-merge, Docker Compose env RL, PostHog/Langfuse sync
```

### 2.2 System Architecture (Identical Locally & in Gradiated Cloud)

```mermaid
flowchart LR
  subgraph Clients["Clients (v0: TS, Python, Go, Rust + `grad` CLI + Customer Environments)"]
    CLI["`grad` CLI (Rust binary)"]
    SDKS["Generated OSS SDKs + Thin Façades<br/>@gradiated/grad · grad-sdk · Go · Rust"]
    ENV["Stateful Customer Environments<br/>(Docker Compose, Seed DBs, MCP Tools)"]
  end

  subgraph RustServer["`server/api` + `server/runtime` (Rust — Thin Server)"]
    API["Axum HTTP API (OpenAPI 3.1)<br/>/v1/endpoints · /v1/artifacts · /v1/trainers · /v1/runs · /v1/trajectories"]
    RT["`grad-runtime`<br/>• Endpoint orchestration (canary/shadow/SLA/cascade/voting)<br/>• In-process ONNX (`ort`, ~5–10 ms CPU)<br/>• Remote LLM proxy (vLLM / SGLang / Gradiated GPU)"]
    SINK["Outbound OTLP GenAI Sink<br/>(10+ providers, <=3.5 MB batches)"]
    API --> RT
    API --> SINK
  end

  subgraph PythonWorker["`server/trainer` (Python — CPU default / GPU pool)"]
    TR["Trainer & Recipes<br/>Frozen Dual-Head (CPU/GPU) · Classifiers · LoRA SFT/DPO/GRPO/OPD · Cartridges"]
    CONN["Inbound Trace Parsers & Sync<br/>(Parquet/JSONL + PostHog/Langfuse/Braintrust/LangSmith...)"]
  end

  subgraph Infra["Backing Stores (Local Docker Compose ↔ Gradiated Cloud)"]
    DB[(PostgreSQL<br/>Endpoints, Artifacts, Jobs, Cursors)]
    VK[(Valkey<br/>Online SLA State + Local Job Queue)]
    OBJ[(Object Store<br/>Local Volume / MinIO ↔ AWS S3<br/>Trajectories, TensorRefs & .grad Artifacts)]
  end

  EXT["External Trace Providers<br/>(PostHog, Langfuse, Braintrust,<br/>LangSmith, Phoenix, Datadog...)"]

  Clients -->|OpenAPI 3.1 HTTP| API
  RT <--> VK
  API --> DB
  API -->|batch jobs / session proxy| PythonWorker
  PythonWorker <--> OBJ
  RT -->|hot-loads .grad| OBJ
  CONN <-->|pull API| EXT
  SINK -->|push OTLP GenAI| EXT
```

---

## 3. Core Data & Artifact Schemas

### 3.1 `Trajectory` (`grad.trajectory/1`) — Universal Model-Agnostic Record

One unified record for production observability traces, supervised `(input → expected_output)` examples, multimodal inputs, and multi-turn RL rollouts (managed recipes work directly on `Trajectory`; custom training loops build tokenizer-bound `Datum`s):

```json
{
  "schema": "grad.trajectory/1",
  "id": "traj_9f82a1...",
  "session_id": "sess_42",
  "group_id": "grp_prompt_42",
  "role": "rollout",
  "source": "posthog",
  "input": {
    "messages": [{ "role": "user", "content": "Refund order #8821" }],
    "tools": [{ "name": "issue_refund" }],
    "media": [{ "kind": "image", "ref": "s3://.../screenshot.png" }],
    "features": { "customer_tier": "enterprise", "turn_index": 0 },
    "payload": null
  },
  "output": {
    "turns": [{ "role": "assistant", "content": "Refund issued." }],
    "token_ids": [151644, 8948],
    "turn_ids": [0, 0],
    "response_offset": 1,
    "sampling_logprobs": [0.0, -0.12],
    "loss_mask": [0.0, 1.0],
    "weight_version": "v12",
    "payload": null
  },
  "expected_output": null,
  "scores": { "task_success": 1.0, "user_thumbs": 1.0 },
  "metrics": { "cost_usd": 0.01105, "latency_ms": 4210, "input_tokens": 1820, "output_tokens": 240 },
  "metadata": { "endpoint": "support-router", "artifact": "support-router@v12", "inference_id": "inf_01J9Y...", "propensity": 0.10, "is_probe": true },
  "timestamp": "2026-11-25T18:00:05Z"
}
```
- Atomic `.append_env_tokens(tokens, turn_id)` helper on `Trajectory` appends tool/RAG/verifier tokens with `loss_mask = 0.0`, `sampling_logprobs = 0.0`, and `weight_version = "env"` in lockstep (eliminating 4-array misalignment bugs in multi-turn RL).
- Built-in `.to_datum(advantage=..., advantages=..., ref_logprobs=..., teacher_topk=..., scalar=...)` SDK helper converts a `Trajectory` directly into a custom-loop `Datum` (copying `token_ids`, `loss_mask`, `sampling_logprobs`, `turn_ids`, `response_offset` and auto-broadcasting scalar `advantage` to length `T`).

### 3.2 `Artifact` (`.grad`, `grad.artifact/1`) — Always Strictly One Immutable Model

Every trained checkpoint, base model reference, or ephemeral RL snapshot is a single immutable `Artifact`:

```text
artifacts/<project_id>/<artifact_name>/<version>/
├── manifest.json             # schema, model_type, runtime adapter id, model_spec, tokenizer digest,
│                             # input/output schema, runtime_hooks (e.g. steering vector, grammar), lineage
├── files/                    # runtime-specific payload:
│                             #   onnx_dual_head: encoder.onnx, tokenizer.json, weights.safetensors, memory_index.bin
│                             #   onnx_classifier: encoder.onnx, tokenizer.json, head.safetensors
│                             #   vllm_lora / sglang_adapter: adapter_config.json, adapter_model.safetensors, base_model_ref
│                             #   cartridge_kv: prefix_kv.safetensors, base_model_ref
│                             #   gbdt: model.onnx
└── eval_report.json          # held-out metrics, 95% bootstrap CIs, task-specific curves (e.g. Pareto savings)
```

### 3.3 `Endpoint` (`grad.endpoint/1`) — Live Production Serving Over 1 or Many `Artifact`s

An `Endpoint` is the live named production slot (`POST /v1/endpoints/{name}/infer` + `POST /v1/feedback`). It cleanly separates **production serving & multi-model orchestration** from raw immutable model weights:

```json
{
  "schema": "grad.endpoint/1",
  "id": "ep_01J9X...",
  "project_id": "default",
  "slug": "support-agent-router",
  "kind": "router",
  "routing": {
    "active": { "artifact": "support-agent-router@2026-11-25-1", "weight": 0.90 },
    "canary": { "artifact": "support-agent-router@2026-11-26-1", "weight": 0.10 },
    "shadow": null
  },
  "strategy": {
    "kind": "sla_lagrangian",
    "actions": [
      { "id": "gpt-4.1-mini", "metadata": { "provider": "openai", "model": "gpt-4.1-mini" },
        "cost_model": { "input_per_1m_usd": 0.40, "output_per_1m_usd": 1.60, "cached_input_per_1m_usd": 0.10 } },
      { "id": "claude-opus-4-7", "is_fallback": true, "metadata": { "provider": "anthropic", "model": "claude-opus-4-7" },
        "cost_model": { "input_per_1m_usd": 5.00, "output_per_1m_usd": 25.00, "cached_input_per_1m_usd": 0.50 } }
    ],
    "sla": {
      "max_quality_drop": 0.02,
      "hard_stop_drop": 0.05,
      "fallback_probe_rate": 0.10,
      "cold_start_probe_rate": 0.05,
      "pessimism_z": 0.8,
      "decay_half_life_episodes": 200
    }
  },
  "capture_dataset": "support-router-prod",
  "online_learning": { "enabled": true, "auto_retrain_min_new_trajectories": 500 }
}
```

**Supported `Endpoint.strategy.kind` presets (1 or many `Artifact`s):**
- `direct` — pass-through single artifact (e.g. `diff_merge`, embeddings, classifiers).
- `sla_lagrangian` — calibrated Pessimistic LCB + `10%` IPS fallback probes + primal-dual `λ` + circuit breaker (`router`).
- `confidence_fallback` — temperature/conformal calibration + threshold fallback (`effort_detector`, guardrails).
- `syntax_fallback` — AST/JSON-schema check + fallback (`diff_merge`, structured tool calls).
- `cascade` — multi-artifact chain (`cheap_llm → verifier_artifact → frontier_llm`, FrugalGPT / HybridLLM).
- `best_of_n` / `majority_vote` — multi-sample generation + optional verifier artifact scoring (`GenRM`, test-time scaling).
- `budget_forcing` — forced continuation / token-budget enforcement (`s1`).

---

## 4. External Server Contract (OpenAPI 3.1 — `spec/openapi.yaml`)

Served by Rust `server/api` identically in **local `docker compose`** (`http://localhost:8787`) and **Gradiated Cloud** (`https://api.gradiated.com`). Auth uses `Authorization: Bearer <api_key>` (optional/dev key locally).

### 4.1 Production Serving & Feedback (`Endpoint` Plane)

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/v1/endpoints` | Create a live endpoint (artifact(s), canary/shadow split, serving strategy, capture dataset) |
| `GET` / `PATCH` / `DELETE` | `/v1/endpoints/{name}` | Read, update traffic split/strategy/SLA, or archive |
| `POST` | `/v1/endpoints/{name}/promote` | Promote `{ "artifact": "name@version", "mode": "active \| canary \| shadow", "weight": 0.1 }` or rollback |
| `GET` | `/v1/endpoints/{name}/status` | Live serving telemetry (canary comparison, rolling IPS drop vs fallback, `λ`, offload %, USD saved) |
| `POST` | `/v1/endpoints/{name}/infer` | **Universal production inference** (`{ input, trace_id?, session_id?, options? }` → `{ inference_id, endpoint, artifact, output, metadata, latency_ms, trace_metadata }`). Fail-open to configured fallback on timeout/circuit-breaker; auto-logs `Trajectory`. |
| `POST` | `/v1/feedback` | **Universal delayed/online feedback** (`events[]`: `inference_id` or `trace_id`, `idempotency_key`, `score?`, `scores{}`, `expected_output?`, `metrics{}`, `evaluator_kind`). Deduplicates, updates online `Endpoint` SLA/canary state in Valkey, and attaches to stored `Trajectory`. |

*Optional Zero-Hop Proxy Mode (Gradiated Cloud Gateway):* `product/services/gateway` embeds `grad-runtime` directly on `/v1/chat/completions`, `/v1/responses`, `/v1/messages` for `router` endpoints (`"model": "<org>/<endpoint-slug>"`), returning `x-gradiated-inference-id`, `x-gradiated-action`, and `x-gradiated-artifact` with zero extra RTT.

### 4.2 Direct Immutable Model Operations (`Artifact` Plane)

Unifies base models (`Qwen/Qwen3-32B`), pinned versions (`support-router@v12`), and ephemeral RL snapshots (`trainer.snapshot()`):

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/v1/artifacts` / `/v1/artifacts/{id}` | List or inspect immutable `.grad` artifacts (`manifest`, `eval_report`, `lineage`) |
| `GET` | `/v1/artifacts/{id}/download` | Download `.grad` bundle |
| `POST` | `/v1/artifacts/merge` | Zero-GPU weight-space merge (`artifacts[]`, `weights[]`, `method`: `linear \| ties \| dare \| slerp`, `density`) → new immutable `.grad` artifact |
| `POST` | `/v1/artifacts/{id}/infer` | Direct read-only inference on a pinned artifact (evals, calibration, hard-negative mining); accepts single `input` or batched `inputs[]` (`artifact.infer()` / `artifact.infer_batch()`). Always returns `heads: { <name>: Tensor }` for every attached head (with `logits` alias for single-head/LM models), respecting `token_level: true` (`(L, dim)`) identically to `Trainer.forward()`. |
| `POST` | `/v1/artifacts/{id}/sample` | Generate `Trajectory` rollouts returning **exact `token_ids` + 1:1 aligned `sampling_logprobs` + `response_offset`**; supports `temperature`, `top_p`, `stop` (strings or token IDs), `seed`, `resume_from`, `append_env_tokens` (atomic `loss_mask=0` observation injection), and optional `response_format` JSON-schema grammar constraints |
| `POST` | `/v1/artifacts/{id}/score-logprobs` | Score full sequences / `Trajectory` objects (`sequences[]`, ideal for multi-turn RL) OR separate `(prefix_tokens, response_tokens)` pairs, returning 1:1 `aligned_logprobs` (plus `response_logprobs` when split); supports `top_k>0`, explicit `candidate_tokens` (for dynamic per-request prompted choice distributions), and `return_layers: int[]` returning opaque `TensorRef`s |
| `POST` | `/v1/artifacts/{id}/embed` | Frozen forward embedding / hidden-state extraction (cached; supports optional `pool`: `mean \| last \| mean_last \| none` and `return_layers`) |
| `POST` | `/v1/artifacts/{id}/tokenize` | Authoritative server-side tokenization & chat-template rendering (`messages`, `tools`, `media` `MediaRef[]`, optional `return_loss_mask: true` for assistant-only multi-turn SFT masking; prevents client/server tokenizer drift across TS, Go, Rust, Python) |
| `GET` | `/v1/tensors/{ref_id}` | Binary Safetensors/Arrow fetch for opaque `TensorRef`s (keeps 152K-vocab logits & hidden states out of JSON) |

### 4.3 Training Plane (Managed Recipes + Interactive Compute Primitives)

#### Managed Training Runs
| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/v1/runs` | Enqueue a managed `Recipe` or multi-stage `Pipeline` run (`202 Accepted` + `run_id`). SDK accepts strict entities (`Dataset`, `Model`/`Artifact`, `Secret`) and typed composable classes (`SFTRecipe`, `adapters.LoRA`, `losses.*`, `optim.AdamW`, `splits.BySession`, `calibration.*`, `Rubric`); dataset filtering lives on `Dataset.filter(...)`. SDK exposes `.wait(on_metric=...)` and `.deploy(canary=...)`; CLI exposes `--dry-run`, `--json`, `grad runs inspect <id> --yaml`, and `grad train -f recipe.yaml`. |
| `POST` | `/v1/runs/plan` | Zero-cost pre-flight dry run (`--dry-run` / `client.runs.plan(...)`): validates dataset coverage, surfaces data warnings, returns resolved `recipe_spec` + estimated training tokens and cost before launching jobs |
| `GET` | `/v1/runs/{run_id}` | Status, progress, resolved `recipe_spec`, `eval_report`, produced `artifact_id` |
| `GET` | `/v1/runs/{run_id}/metrics` | Structured step-by-step telemetry stream (`step`, `loss`, `grad_norm`, `lr`, `eval_metrics`, `tokens_per_sec`) — SSE or paginated JSON |
| `POST` | `/v1/runs/{run_id}/cancel` | Cancel active training job |

#### Interactive Compute Trainers (Custom Loops)
| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/v1/trainers` | Allocate a `Trainer` pinning `model` (`Model` ref or trained `Artifact`), `adapter` (`adapters.FrozenHead`, `adapters.LoRA`, `adapters.DoRA`, `adapters.PrefixKV`, `adapters.LoReFT`, `adapters.PartialUnfreeze`, `adapters.Full`, `adapters.Eagle3Draft`), optional `heads` (`heads.Linear(dim, token_level, trainable)`), optional `pool`, or resume state via `client.trainers.resume(ckpt)` |
| `POST` | `/v1/trainers/{tid}/fit-batch` | Closed-form / convex / calibration fit over embeddings, `TensorRef`s, or raw token `Datum`s (`solvers.DualHeadKernelLBFGS`, `solvers.MeanDiffSteering`, etc.) |
| `POST` | `/v1/trainers/{tid}/forward-backward` | Iterative step: grouped/paired variable-length `Datum[]` (graceful no-op on empty 0-variance batch) + any `Loss` (built-in GPU kernels or client-side `losses.CustomLoss` subclass routed via `/forward` + `/backward-surrogate`) → pipelined async future (`op_id`); RL losses automatically report `kl_sample_train` and `sample_train_max_diff` in step metrics |
| `POST` | `/v1/trainers/{tid}/forward` | Forward pass with explicit `outputs[]` (`logprobs \| topk_logprobs \| logits \| embeddings \| heads \| layers`), optional `gather_indices` (`TensorRef`s for top-K distillation OR inline candidate token IDs for dynamic-choice decision models — never pulls 152K-vocab logits!), `return_layers`, and `retain_graph: bool` (`false` for eval/calibration to avoid GPU graph leaks) |
| `POST` | `/v1/trainers/{tid}/backward-surrogate` | Bit-exact surrogate backward accepting client-computed `dLoss/dOut` (`dLogprobs`, `dTopkLogprobs`, `dLogits`, `dEmb`, `dHeads`, or `dHidden[layer]`) — zero untrusted code on GPU workers. Dispatched automatically when passing a `losses.CustomLoss` subclass to `trainer.forward_backward(datums, loss=...)`. |
| `POST` | `/v1/trainers/{tid}/optim-step` | Apply optimizer step (`optim.AdamW`, `optim.Muon`, `optim.SGD`, dynamic per-step `lr` & `optim.ParamGroup`, grad clip, optional `optim.WeightAnchor(artifact=..., strength=...)` for EWC/L2-SP continual learning) |
| `POST` | `/v1/trainers/{tid}/snapshot` | Hot-snapshot current weights into an ephemeral callable `Artifact` handle (`artifact_id`, `weight_version`) for sync/async RL rollouts & live evals |
| `POST` | `/v1/trainers/{tid}/save-state` | Checkpoint trainer + optimizer state for `client.trainers.resume(ckpt)` (stage chaining passes an `Artifact` as `model=` with a fresh optimizer) |
| `POST` | `/v1/trainers/{tid}/export` | Freeze `(ModelSpec + weights + EvalReport + lineage)` into an immutable `.grad` `Artifact` (optional `merge_adapter: true`) |
| `DELETE` | `/v1/trainers/{tid}` | Release GPU/CPU trainer lease |

### 4.4 Trajectories, Imports, Inbound Sources & Outbound Sinks

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/v1/trajectories` | Push `grad.trajectory/1` records directly into a dataset from application code or eval scripts (`trajectories.push()`) |
| `POST` | `/v1/trajectories/imports` | Stream raw file (`format`: `grad_trajectories \| gradiated \| otel \| posthog \| langfuse \| braintrust \| langsmith \| phoenix \| weave \| datadog \| opik \| logfire \| helicone`) |
| `GET` | `/v1/trajectories/imports/{import_id}` | Status, parsed trajectory count, dropped count, detected `scores` keys |
| `POST` / `GET` / `PATCH` / `DELETE` | `/v1/trajectories/sources` | Scheduled incremental pull sync from external provider (secret ref, filter, schedule cron, opaque `cursor`) |
| `POST` | `/v1/trajectories/sources/{source_id}/sync` | Trigger immediate incremental pull |
| `POST` / `GET` / `PATCH` / `DELETE` | `/v1/trajectories/sinks` | *(Deferred to Phase 2)* Outbound sync FROM Gradiated trajectories INTO external provider (OTLP GenAI preset or Helicone; `include_content` redaction) |

---

## 5. Stateful Environments, `Datum` Invariants & Composable Recipes

### 5.1 Stateful `Environment` Lifecycle (Complex Docker Compose Stacks & Seed Scripts)

Environments run **outside the GPU training cluster** (customer CPU boxes, Kubernetes, or optional managed sandbox pools) and talk to `Artifact` / `Trainer` over HTTP. To cleanly support complex stateful apps (Postgres + Redis + Backend API + `seed.sh`) under parallel GRPO rollouts, `Environment` exposes **4 explicit lifecycle hooks** where `Rubric` evaluates against **live environment state BEFORE teardown**:

```python
class DockerComposeEnv(Environment):
    def setup(self, task: dict, rollout_id: str) -> EnvHandle:
        # Isolated Compose project (`COMPOSE_PROJECT_NAME=r_<id>`) OR fast warm-pool lease
        # with DB template restore (`CREATE DATABASE ... TEMPLATE seed_db` / `./seed.sh` ~50 ms)
        ...

    def step(self, handle: EnvHandle, action: Action) -> Observation:
        # Executes agent MCP/tool call against `handle.base_url`;
        # returning `Observation(text=..., done=False)` auto-tokenizes via `artifact.tokenize()`
        # and appends via `trajectory.append_env_tokens(..., loss_mask=0.0)` (raw `tokens=` also supported).
        ...

    def evaluate(self, handle: EnvHandle, trajectory: Trajectory) -> dict[str, float]:
        # Runs Rubric BEFORE teardown — can query live Postgres / Redis / API / filesystem via `handle`!
        return self.rubric.score(trajectory, state=handle)

    def teardown(self, handle: EnvHandle) -> None:
        # Guaranteed in `finally:` + TTL reaper so timed-out rollouts never leak containers/volumes
        ...
```

### 5.2 `Datum` & Universal 1:1 Token-Alignment Invariant

For any `tokens` sequence of length `T`, **every** per-token array (`loss_mask`, `sampling_logprobs`, `ref_logprobs`, `advantages`, `step_rewards`, and returned `forward.logprobs`) has **exact length `T`**, where index `i` is the prediction of `tokens[i]` given `tokens[:i]` (index `0` is always `0.0` / masked):

```json
{
  "group_id": "grp_prompt_42",
  "role": "rollout",
  "model_input": {
    "tokens": [151644, 8948, 220, 15],
    "turn_ids": [0, 0, 1, 1],
    "media": [{ "kind": "image", "ref": "s3://.../screen.png" }],
    "embedding": null,
    "features": { "turn_index": 0 }
  },
  "targets": {
    "loss_mask": [0.0, 0.0, 1.0, 1.0],
    "response_offset": 2,
    "positions": null,
    "labels": null,
    "label": null,
    "scalar": null,
    "sampling_logprobs": [0.0, 0.0, -0.41, -0.12],
    "ref_logprobs": [0.0, 0.0, -0.39, -0.15],
    "teacher_topk": null,
    "advantages": [0.0, 0.0, 1.12, 1.12],
    "step_rewards": null,
    "cost_usd": null
  }
}
```
- `group_id` + `role` (`chosen`/`rejected`/`anchor`/`positive`/`negative`/`desirable`/`undesirable`/`rollout`) keeps pairs/groups atomic across microbatches (DPO, RM, InfoNCE, ColBERT, GRPO).
- `response_offset` aligns split-prefix distillation (`teacher_topk`, accepting one `TensorRef` or a weighted list for multi-teacher ensembles).
- `positions` + `labels` support sparse multi-position targets (Math-Shepherd step PRMs, LLMLingua-2 token compression).
- **Anti-bloat rule:** Keep ~11 workhorse built-in losses in OpenAPI; exotic variants (`GSPO`, `Dr. GRPO`, `KTO`, `ORPO`, `SPPO`, `Matryoshka MRL`, `RMU`, `BGE-M3`) run via the SDK's `trainer.forward_backward_custom(datums, outputs, loss_fn)` helper over `/forward` + `/backward-surrogate` (verified bit-exact `0.00e+00`) or Python loss plugins without touching OpenAPI/SDKs.

### 5.3 Progressive Disclosure: Managed Recipes → Custom Loops

- **Managed recipes (default path):** Explicitly pick the recipe (`router`, `classifier`, `sft`, `dpo`, `grpo`, `distill`, `cartridge`). Every recipe ships with smart defaults (`grad train --dataset support-prod --name support-router --recipe router --wait`), exports its full resolved config (`grad runs inspect <id> --yaml > recipe.yaml`), and accepts typed top-level fields (`base`, `adapter`, `loss`, `optimizer`, `split`, `filter`, `calibration`) without writing a loop.
- **Custom loops (full control):** Drive `Trainer`, `Artifact` (`trainer.snapshot()`), `Environment`, and `Rubric` directly — verified end-to-end across **60 diverse papers** (Model Router, Effort Detector, Diff-Merge SFT→GRPO, DAPO, GSPO, CISPO, Kimi k1.5, OPD, Cartridges, Online DPO, KTO, ORPO, IPO, SimPO, SPPO, SPIN, NPO, VAPO, PRIME, AZR, RMU, Matryoshka+ColBERT, Math-Shepherd, EAGLE-3, Medusa, MTP, VLM GRPO, LoReFT, TIES/DARE Merge, RepE Steering, Search-R1, SCoRe, ArCHer, SPIRAL, Toolformer, ArmoRM, GenRM, SaySelf, s1, Conformal, RouteLLM, FrugalGPT, BGE-M3, SetFit, LLMLingua-2).

---

## 6. Client Strategy: Rust `grad` CLI + High-Quality OSS-Generated SDKs (v0: TS, Python, Go, Rust)

### 6.1 Open-Source SDK Generation Pipeline

Every v0 SDK uses a **two-layer structure** — 100% open-source generated transport (`_generated/`) from `spec/openapi.yaml` wrapped in a **thin (~200 LOC) hand-written idiomatic façade** + a shared wire-level contract test suite in CI:

| Language | Package | OSS Generator | Idiomatic Façade Highlights |
| --- | --- | --- | --- |
| **TypeScript / JS** | `@gradiated/grad` (npm) | **`@hey-api/openapi-ts`** | Native `fetch` (Node, Bun, Deno, Edge), retries, generic `grad.endpoint(...).infer<TIn, TOut>()`, typed presets (`grad.router(...)`), local `Rubric` runner, `wrapOpenAI` / `wrapAnthropic` / Vercel AI SDK helpers, OTel stamper. |
| **Python** | `grad-sdk` (PyPI) | **`openapi-python-client`** | Sync (`Grad`) + async (`AsyncGrad` over `httpx`), managed recipe + custom-loop clients (`with client.trainers.create(...) as trainer:`, `runs.create(...).wait(on_metric=...)`, `run.deploy()`, `trainer.forward_backward_custom`, `trajectory.to_datum`, `artifact.infer_batch`, `snap.openai_client()` trajectory recorder for existing agent harnesses), `Environment` (`Observation(text=...)` auto-tokenized + `max_concurrency`/`timeout_s`) + `Rubric` helpers, OpenAI/Anthropic wrappers, zero server deps (optional `torch` extra only for client-side custom surrogate losses). |
| **Go** | `github.com/Gradiated/grad/sdks/go` | **`oapi-codegen`** | Standard-library `net/http`, `context.Context`, functional options, generic `grad.InferAs[T](...)` + router preset. |
| **Rust** | `grad-sdk` (crates.io) | **`progenitor`** *(Oxide)* | Typed async `reqwest` client with generic `infer_as<T>(...)`, shared by `grad` CLI and Gradiated's Rust services. |

### 6.2 Auto-Generated Primitive, SDK & CLI Reference (Zero-Drift Docs)

Conceptual guides and recipe walkthroughs live as hand-written MDX under `product/website/src/docs/training/`. All **primitive schemas, HTTP endpoints, enum values, SDK signatures, and CLI flags** are generated automatically in CI (failing with `--check` on drift):

| Reference Surface | Single Source of Truth | Generator → Output |
| --- | --- | --- |
| **Wire Primitives & HTTP API** (`Trajectory`, `ModelSpec`, `Datum`, `Trainer`, `Artifact`, `Endpoint`, `Feedback`, all enums & routes) | `spec/openapi.yaml` *(emitted from Rust `server/api` via `utoipa`)* | `scripts/generate-grad-reference.ts` → generated MDX schema/endpoint reference pages in `product/website/src/docs/training/reference/` + interactive OpenAPI at `api.gradiated.com/docs` |
| **Python SDK Façade** (`Environment`, `Rubric`, `Observation`, `forward_backward_custom`, `to_datum`) | `sdks/python/grad/` typed signatures & docstrings | `griffe` JSON AST → MDX reference tables matching website styling |
| **TypeScript SDK Façade** (`Grad`, `router()`, `endpoint()`, `feedback`) | `sdks/typescript/src/` `.d.ts` | TypeScript Compiler API / `typedoc-plugin-markdown` → MDX |
| **`grad` CLI Flags & Subcommands** | `cli/` `clap` command tree | `clap_markdown` → MDX CLI reference |

### 6.3 TypeScript & CLI Ergonomics Preview

```ts
import { Grad } from "@gradiated/grad";

// Reads GRADIATED_API_KEY (and optional GRAD_BASE_URL) automatically, or pass explicitly:
const grad = new Grad({ apiKey: process.env.GRADIATED_API_KEY });

// 1. Model Router Endpoint (candidate models & pricing inferred from trained artifact manifest)
const router = grad.endpoints.get("support-agent-router");
const decision = await router.route({ messages, tools });
const reply = await callLLM(decision.model, messages, tools);
await grad.feedback.record({ inferenceId: decision.inferenceId, score: 1.0, metrics: { cost_usd: 0.0009 } });

// 2. Effort-Level Detector Endpoint
const effort = await grad.endpoints
  .get("coding-effort")
  .infer<{ label: "low" | "medium" | "high" }>({ messages });

// 3. Diff-Merge Generative Endpoint (with gold expectedOutput correction feedback!)
const merged = await grad.endpoints
  .get("fast-diff-merge")
  .infer<{ merged_code: string }>({ payload: { original, snippet } });
await grad.feedback.record({
  inferenceId: merged.inferenceId,
  score: testsPassed ? 1.0 : 0.0,
  expectedOutput: humanFix ? { merged_code: humanFix } : undefined,
});
```

```bash
# Rust `grad` CLI (single static binary via cargo-dist / Homebrew; `--json` on every command)
grad local up                                   # CPU default (`--gpu` enables CUDA trainer & serving)
grad import ./support_traces.jsonl --dataset support-prod   # format auto-detected (`--format` optional)
grad train --dataset support-prod --name support-router --recipe router --dry-run --json
grad train --dataset support-prod --name support-router --recipe router --wait
grad runs inspect run_01J9X --yaml > recipe.yaml
grad deploy support-router@latest --canary 0.10 # 1-line upsert deploy using artifact defaults
grad endpoints status support-router --watch    # live canary & IPS SLA monitor
grad secrets set langfuse-prod
grad sources add langfuse --dataset support-prod --host https://cloud.langfuse.com --secret langfuse-prod --schedule "*/15 * * * *"
```

---

## 7. Bidirectional Trace Provider Integration Matrix

| Tier | Provider | Inbound Export (Offline) | Inbound Sync API | Cost & Existing Scores | Outbound Gradiated → Provider | Provider Quirks |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **T1** | **Gradiated Native** | JSONL / S3 `*.jsonl.zst` | S3 manifest cursor / API | Token usage + pricing; `feedback` | Native collector (`POST /v1/contents`) | Relay records have `canonical=null`; normalize from `raw` (`openai.chat`, `openai.responses`, `anthropic.messages`). |
| **T1** | **OTEL / OpenInference** | OTLP JSONL / Parquet | OTLP Collector / cursor | `gen_ai.usage.*`; span attrs | Generic OTLP/HTTP Protobuf (`/v1/traces`) | Support both GenAI SemConv v1.37+ (`gen_ai.*`) and OpenInference (`llm.*`). |
| **T1** | **Langfuse** | UI CSV/JSONL; S3 Parquet/JSONL | `GET /api/public/traces` + `/observations` + `/scores` | `calculatedTotalCost`; `/scores` | **OTLP:** `https://[us.]cloud.langfuse.com/api/public/otel/v1/traces` (`Basic pk:sk`) | Join `/scores` separately by `traceId`/`observationId`. |
| **T1** | **PostHog** | S3/R2 Batch **Parquet**; HogQL CSV/JSON | HogQL `POST /api/projects/{id}/query/` (`$ai_generation`) | `$ai_total_cost_usd`; joined events | **OTLP:** `https://[us\|eu].i.posthog.com/i/v0/ai/otel` (`Bearer <project_token>`) | Group flat events by `$ai_trace_id`. OTLP cap **4 MB uncompressed**; only `gen_ai.`/`llm.`/`ai.`/`traceloop.` spans kept. |
| **T1** | **Braintrust** | BTQL JSONL/CSV | `POST /btql` (`shape => 'traces'`, `pagination_key`) | `metrics.estimated_cost`; inline `scores` (`0..1`) | **OTLP:** `https://api[-eu].braintrust.dev/otel/v1/traces` (`Bearer` + `x-bt-parent: project_id:<id>`) | Use `project_id:` (not name) in `x-bt-parent`. |
| **T1** | **LangSmith** | S3/GCS/MinIO Bulk **Parquet** | `POST /api/v2/runs/query` + `GET /api/v1/feedback` | `total_cost`; feedback `key`/`score`/`value` | **OTLP:** `https://[eu.\|aws.]api.smith.langchain.com/otel/v1/traces` (`x-api-key` + `Langsmith-Project`) | OTLP `run_id` = lower 8 bytes of OTel `span_id` zero-padded to UUID; wrong ID returns `202` orphan. |
| **T2** | **Arize Phoenix** | `get_spans_dataframe()` Parquet/JSONL | `GET /v2/projects/{id}/spans` + annotations | Tokens + Span Annotations (`HUMAN`/`LLM`) | **OTLP:** `<endpoint>/v1/traces` or `:4317` | Group flat spans by `context.trace_id`. |
| **T2** | **Datadog LLMObs** | Span archive / UI export | `POST /api/v2/llm-obs/v1/spans/events/search` | `metrics.total_cost` + Evaluations | **OTLP:** `https://otlp.<DD_SITE>/v1/traces` (`DD-API-KEY` + `dd-otlp-source: llmobs`) | Needs API + App key to pull. Writing evals to OTel spans needs `"source:otel"` + hex→decimal IDs. |
| **T2** | **W&B Weave** | SDK `get_calls()` Parquet/JSONL | `POST /calls/stream_query` + `/feedback/query` | `summary.usage`; feedback reactions/scorers | **OTLP:** `https://trace.wandb.ai[/agents]/otel/v1/traces` (`wandb-api-key` + `project_id`) | Streaming NDJSON pull; prefer `/agents/otel/v1/traces` for agents. |
| **T2** | **Comet Opik** | UI/SDK JSON/CSV | `GET /api/v1/private/traces` (`from_time`/`to_time`) | `total_estimated_cost`; inline `feedback_scores` | **OTLP:** `https://www.comet.com/opik/api/v1/private/otel/v1/traces` | Needs `Comet-Workspace` + `projectName` headers. |
| **T2** | **Pydantic Logfire** | Query API Arrow/Parquet | `POST /v2/query` (SQL over `records`, Read Token) | OTel `gen_ai.*` attributes | **OTLP:** `https://logfire-{us\|eu}.pydantic.dev/v1/traces` | SQL cursor (`WHERE start_timestamp > $cursor`); returns Arrow directly. |
| **T2** | **Laminar (`lmnr`)** | UI/SQL export | REST/SQL query API | Built-in cost + evaluator scores | **OTLP:** `https://api.lmnr.ai/v1/traces` or `:8443` | Standard OTel native support. |
| **T2** | **Helicone** | `npx @helicone/export` JSONL/CSV | `POST /v1/request/query-clickhouse` | `costUSD`; `scores` map + properties | **Custom JSON (No OTLP):** `POST https://api.worker.helicone.ai/custom/v1/log` | Property filters MUST wrap inside `request_response_rmt.properties`. Group turns via `Helicone-Session-Id`. |

*Shared `OTLPGenAISink` inside Rust `server/api` enforces `max_batch_bytes = 3_500_000` (under PostHog's 4 MB cap), supports `include_content: false` redaction, and uses secret refs (env vars locally; KMS/Secrets Manager in Cloud) so provider keys never appear in configs or `.grad` manifests.*

---

## 8. Local Docker Compose vs. Gradiated Cloud Parity

| Component | Local (`server/docker-compose.yml`) | Gradiated Cloud |
| --- | --- | --- |
| **Thin Server & Runtime** | `grad-server` (Rust Axum + `grad-runtime` on `:8787`) | `grad-server` + `grad-runtime` embedded in `product/services/gateway` |
| **Python Trainer & Sync Worker** | `grad-trainer-cpu` (default) + optional `grad-trainer-gpu` (`--profile gpu`) | Temporal GPU + CPU worker pools |
| **Generative Model Serving** *(e.g. diff-merge)* | Optional local vLLM/SGLang/Ollama container (`--profile gpu`) | Gradiated dedicated GPU serving runtimes (`product/inference/`) |
| **Metadata DB** | PostgreSQL container | Managed PostgreSQL |
| **Online State & Queue** | Valkey container | Managed Valkey + Temporal |
| **Artifacts, Trajectories & Tensors** | Local volume / MinIO (`S3`-compatible) | AWS S3 (KMS-encrypted, per [TRACES_PLAN.md](TRACES_PLAN.md)) |
| **Analytics / Events** | PostgreSQL / DuckDB local tables | ClickHouse |

---

## 9. Paper Reproductions Hub (`gradiated.com/papers/` & One-Click `grad run`)

Separate from `/docs/`, Gradiated ships a public **Paper Reproductions Hub** (`gradiated.com/papers/<slug>/`, backed by `papers/<slug>/` templates) where popular and newly released post-training papers are implemented in 15–60 lines of `grad` against pinned public datasets — acting as the **"one-click deploy button" equivalent for ML research**.

### 9.1 Template Contract (`papers/<slug>/paper.yaml`)

Each paper directory is self-contained and machine-runnable:

```yaml
# papers/sdft/paper.yaml
slug: sdft
title: "Self-Distillation Fine-Tuning (SDFT)"
arxiv: "https://arxiv.org/abs/2601.19897"
category: distillation
public_dataset: "hf://sciknoweval/chemistry-demo"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py            # or recipe.yaml for managed recipes
estimate: { tokens_millions: 4.5, minutes: 18, approx_usd: 1.40 }  # metered per-1M tokens + saved weight storage
```

### 9.2 Three Zero-Friction Launch Paths

1. **One-click Web Launch (Console Deep-Link):**
   `https://console.gradiated.com/run?template=papers/sdft&base=Qwen/Qwen3-8B` opens the Gradiated Console pre-filled with the paper's recipe, pinned public dataset, `$0` dry-run cost/time estimate, and a single **Run** button — plus an embeddable **"Run on Gradiated"** README badge for paper authors.
2. **One-command CLI (`grad run` / `grad init`):**
   ```bash
   grad run papers/sdft --dry-run    # validate pinned public dataset + estimate time & cost ($0)
   grad run papers/sdft --wait       # stream live metrics, compare vs. paper table, export .grad
   grad init papers/sdft             # copy the ~30-line script locally to modify loss or data
   ```
3. **Coding-agent handoff:** Every `/papers/<slug>/` page exposes **Copy Markdown** and **Copy prompt** so a researcher can drop the paper reproduction straight into Claude Code or Codex and adapt it to their own dataset.

### 9.3 Launch Slate, 50-Paper Smell Audit & Day-0 Paper Drops

Every page reports **measured** Gradiated runs (wall-clock time, USD cost, learning curve, and eval delta) clearly distinguished from **paper-reported** numbers. All **50 flagship post-training papers** (`grpo`, `dapo`, `dr-grpo`, `gspo`, `cispo`, `rloo`, `reinforce-plus-plus`, `vapo`, `dpo`, `simpo`, `orpo`, `kto`, `ipo`, `online-dpo`, `spin`, `sdft`, `cartridges`, `gkd`, `minillm`, `distillm`, `llmlingua-2`, `math-shepherd`, `prime`, `armorm`, `genrm`, `vineppo`, `safe-rlhf`, `search-r1`, `score`, `absolute-zero`, `archer`, `toolformer`, `spiral`, `routellm`, `s1`, `eagle-3`, `medusa`, `repe`, `kimi-k1-5`, `dora`, `lora-plus`, `loreft`, `ties-merging`, `rmu`, `npo`, `matryoshka-colbert`, `bge-m3`, `setfit`, `sayself`, `vlm-grpo`) are published at `/papers/<slug>/` and verified end-to-end in PyTorch (`50/50 PASS`).

Implementing all 50 papers surfaced **7 concrete API smells** that were resolved with **0 new primitives** (1 small server-side loss option + 6 pure-SDK helpers):
1. **Server-side multi-horizon head CE (`cross_entropy` `heads: { name: { shift, weight } }`):** eliminates transferring `(B, L, 152k)` vocab logits over HTTP for Medusa and DeepSeek-V3 MTP heads.
2. **`grad.group_datums(groups, rewards=..., norm="std"|"mean"|"rloo"|"none", skip_zero_var=True, ref_logprobs=...)`:** collapses 8–10 lines of repeated `pstdev`/`fmean`/`ref_iter` plumbing across 13 RL papers into 1 line.
3. **Pre-tensorized `forward_backward_custom` target views + `grad.masked_mean()`:** auto-populates `out["masks"]` *(with `mask[0] == 0.0` enforced)*, `out["sampling_logprobs"]`, `out["ref_logprobs"]`, `out["advantages"]`, and `out["turn_ids"]`.
4. **`grad.by_group(datums, out)`:** replaces fragile positional `range(0, len, 2/3)` slicing with shuffle-safe `group_id` + `role` grouping (`chosen`/`rejected`, `anchor`/`positive`/`negative`).
5. **Batched `TensorRef` fetching:** `forward_backward_custom(..., gather_indices=refs)` auto-batch-fetches `out["teacher_topk_logprobs"]` in 1 RPC (`GKD`, `DistiLLM`), and `client.tensors.fetch_batch(refs)` batches arbitrary layer activation refs (`RMU`).
6. **`Artifact.to_datum(messages=..., media=...)` & `Trajectory.slice_prefix(end_idx)`:** removes `tokenize`→`Datum` dict-unpacking boilerplate and manual prefix slicing (`VinePPO`).
7. **Ergonomic `Trajectory` / `resume_from` defaults:** `Artifact.sample(resume_from=...)` no longer requires redundant `prompts`, and `Artifact.infer_batch()` accepts `Trajectory` lists directly.

---

## 10. Phased Rollout

- **Phase 0 — `Gradiated/grad` v0 (Private Repo, OSS-Ready):**
  - Lock `spec/openapi.yaml` (validated from Rust `server/api` via `utoipa`).
  - Build Rust `server/api` + `server/runtime` (`onnx_runner`, `endpoint_policy` w/ Valkey Pessimistic LCB/IPS SLA + canary/shadow, `remote_llm` proxy).
  - Build Python `server/trainer` (5 core primitives, managed recipes: `router` [33M CPU + `Qwen3-0.6B` GPU], `classifier`, Tier-1 trace connectors: `Gradiated`, `OTEL`, `Langfuse`, `PostHog`, `Braintrust`, `LangSmith`, `grad_trajectories`) + `server/docker-compose.yml` (CPU + `--profile gpu`) + `server/helm/grad/`.
  - Ship Rust `grad` CLI + OSS-generated v0 SDKs with idiomatic façades & shared wire-level contract tests for **TypeScript, Python, Go, and Rust**.
  - End-to-end verification on AppWorld + CRMArena-Pro fixtures.
- **Phase 1 — Gradiated Cloud Hosting, Interactive Compute API & Generative/RL Recipes:**
  - Deploy `server/` into Gradiated Cloud (Temporal + S3 + ClickHouse); embed `grad-runtime` into `product/services/gateway` for zero-hop proxy routing.
  - Expose public `/v1/trainers/*`, `/v1/artifacts/{id}/{sample,score-logprobs,embed,tokenize}`, `/v1/tensors/{ref_id}`, and `POST /v1/artifacts/merge`, plus `sft`, `dpo`, `grpo` (with stateful `DockerComposeEnv` support), and `distill` recipes.
  - Add Console UI (Pareto curves, canary/SLA monitors, trajectory source setup).
- **Phase 2 — Public OSS Release & Expansion:**
  - Tier-2 trace sources (`Phoenix`, `Datadog`, `Weave`, `Opik`, `Logfire`, `Laminar`, `Helicone`) + outbound sinks (`OTLPGenAISink`, `HeliconeSink`).
  - Managed sandbox pool for customer `docker-compose.yml` environments, additional recipes (`Cartridges`, `GenRM`, `EAGLE-3`, `BGE-M3`).
  - Flip `Gradiated/grad` public.
