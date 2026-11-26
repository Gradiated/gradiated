# Training Platform Architecture & v0 Plan

- status: proposed architecture & v0 scoping authority
- date: 2026-11-26
- related: [ARCHITECTURE.md](ARCHITECTURE.md), [TASK_FINE_TUNING_FLEET_CONTRACT.md](TASK_FINE_TUNING_FLEET_CONTRACT.md), [TASK_FINE_TUNING_SERVING_CONTRACT.md](TASK_FINE_TUNING_SERVING_CONTRACT.md), [CARTRIDGE_SERVING_PLAN.md](CARTRIDGE_SERVING_PLAN.md), [AWS_GPU_PROVIDER_PLAN.md](AWS_GPU_PROVIDER_PLAN.md)

This document defines how the Gradiated training platform (`grad-server`, `grad-trainer`, and the `grad` SDK/CLI) fits alongside our existing production inference stack, how it stays self-hostable from day one, how training compute and sandboxes are isolated, and what is scoped into v0 versus deferred.

## Core Decisions

1. **Portable `grad-server` core (Postgres + S3 only):** The training control plane runs as its own service in a dedicated EKS namespace (`training`) with its own Postgres database and S3 bucket (`gradiated-training-prod`). It never imports Valkey, ClickHouse, or Better Auth internals directly. Cloud capabilities (auth, token billing, hosted deploy) plug in through three narrow adapters so `grad local up` (Docker Compose), the self-hosted Helm chart, and Gradiated Cloud run the exact same codebase.
2. **LoRA & Cartridges only for LLMs (no `adapters.Full()`):** Every LLM training run produces a small adapter (`LoRA`) or `PrefixKV` Cartridge (~100–300 MB trainable state). This enables multi-tenant parallel LoRA training on shared base weights, compact S3 checkpoints, and guaranteed hot-loading onto shared SGLang serving pools via `ART-01`/`SERV-01`. `EmbeddingRecipe` (`baai/bge-small-en-v1.5`, 33M params) trains its full encoder weights internally.
3. **Per-token billing:** All v0 recipes are offline and throughput-deterministic, billed per million tokens processed (matching inference billing and enabling accurate `runs.plan()` cost estimates).
4. **Simple `deploy()` on existing serving contracts:** Drop traffic-splitting canaries, shadow mirroring, and automated quality-drop rollback for v0. `artifact.deploy()` / `grad deploy` maps 1-to-1 onto existing `ART-01` validation, `/internal/adapters/probe` qualification, and atomic `SERV-03` pointer promotion (`tasks.production_version_id` → Valkey). Rollback is deploying an earlier version.
5. **Hard isolation between serving, training, and sandboxes:** Production serving GPUs never run training jobs; training GPUs run in an isolated AWS account/pool with no AWS/DB/Temporal credentials; untrusted customer code/environments (post-v0) run in a separate sandbox AWS account via AWS Lambda MicroVMs behind the same rollout-worker protocol as `grad env serve`.
6. **v0 recipe scope (6 recipes, full SDK surface preserved):** Ship `SFTRecipe`, `DPORecipe`, `RouterRecipe`, `DecisionModelRecipe`, `CartridgeRecipe`, and `EmbeddingRecipe` in v0. Keep typed SDK definitions for `DistillRecipe`, `RewardModelRecipe`, `GRPORecipe`, and `Environment` so the SDK contract does not break when Wave 2 lands.

## System Topology

```text
                       ┌───────────────────────────────────────────────┐
                       │   grad-server (EKS `training` namespace)      │
                       │   Own Postgres DB · Own S3 bucket             │
                       │   (Same image ships in Docker Compose / Helm) │
                       └───────┬──────────────────────────┬────────────┘
                               │                          │
           Cloud adapters (3 narrow HTTP/RPC bridges)     │
           • Auth: validate key/workspace via `api`       │
           • Billing: balance check + token usage -> api  │
           • Deploy: ART-01 publish + SERV-03 promote     │
                               │                          │
     ┌─────────────────────────▼───────┐      ┌───────────▼─────────────────────────┐
     │  SERVING PLANE (Existing)       │      │  TRAINING PLANE (Isolated)          │
     │                                 │      │                                     │
     │  • `api` + `worker` (EKS)       │      │  • Orchestration:                   │
     │  • Rust `gateway` + Valkey      │      │    - Cloud: Temporal Cloud + VK     │
     │  • Production SGLang Pool       │      │    - Self-hosted: PG queue + K8s    │
     │    (RunPod + gradiated-gpu-prod)│      │  • Dedicated Training GPU Pool      │
     │  • Host-owned loader (SERV-01)  │      │    (separate AWS acct / taint)      │
     │    LoRA + Cartridges + SystemOne│      │  • `grad-trainer` container         │
     └─────────────────────────────────┘      └──────────────────▲──────────────────┘
                                                                 │
                                              Post-v0 RL Rollout Worker Protocol
                                              • v0/v1: `grad env serve` (user laptop/VM)
                                              • v1: AWS Lambda MicroVMs (gradiated-sandbox-prod)
                                              • v2: Pre-baked Ephemeral EC2 (heavy Compose repos)
```

## Service Boundaries & Self-Hosting Parity

`grad-server` owns `datasets`, `runs`, `checkpoints`, `artifacts`, `evals`, and `feedback` inside its own Postgres database and S3 bucket. Because it has its own DB credentials, it cannot join against Cloud tables (`organizations`, `api_keys`, `balance_transactions`, `model_deployments`).

| Adapter | Self-Hosted (`grad local up` / Helm) | Gradiated Cloud |
| :--- | :--- | :--- |
| **Auth** | Local `ADMIN_API_KEY_HASH`, Postgres scoped keys, optional OIDC JWT | Delegates bearer token verification to `api` (same pattern as `product/services/mcp`) |
| **Job Scheduler** | Postgres `SKIP LOCKED` job queue + local worker / K8s Jobs (KEDA scale-to-zero) | Temporal Cloud encrypted workflows + Virtual Kubelet dedicated training pool |
| **Metrics & Billing** | Postgres / S3 JSONL; billing is a no-op | Token usage emitted to `api`/ClickHouse settlement; balance gate before launch |
| **Artifact Deploy** | Writes PEFT LoRA / Safetensors to customer S3/GCS; `deploy()` disabled | Calls `api` internal publish/promote (`ART-01` → S3 `adapters/`/`cartridges/` → probe → Valkey) |

CI runs integration tests against the **self-hosted (Postgres + S3 only)** mode on every PR so Cloud remains strictly an additive layer.

## Isolation Boundaries

1. **Serving vs. Training Compute (Hard Isolation):**
   - Training GPUs run on dedicated hosts/taints (`gradiated.com/workload=training:NoSchedule`) in an isolated AWS account (following [AWS_GPU_PROVIDER_PLAN.md](AWS_GPU_PROVIDER_PLAN.md)), with no VPC peering to production RDS/Valkey/EKS.
   - Training hosts receive no Temporal, Postgres, Valkey, or provider API keys—only short-lived presigned S3 grants and the private Tailscale control listener.
   - RL rollouts (post-v0) never hit production customer SGLang replicas; they use dedicated/colocated rollout engines inside the training plane.
2. **Multi-Tenant Training Compute:**
   - Untrusted user Python never executes on GPU nodes.
   - In v0, batch runs execute in isolated per-job containers on dedicated GPU claims. Because all LLM runs are LoRA/Cartridge (~100–300 MB trainable state), the same artifact/checkpoint layout scales directly to multi-tenant LoRA packing on shared base weights later.
3. **Untrusted Environments & Sandboxes (Post-v0):**
   - Executed in a separate `gradiated-sandbox-prod` AWS account with zero Tailscale routes, IMDS blocked, and default-deny egress (`network=False`).
   - **Lightweight & SaaS repos** (`Scorer`, `Tools`, `verifiers`, single-container `Harbor`, Next.js + `postgres`/`redis`/`supabase-lite`): **AWS Lambda MicroVMs** (Firecracker hardware isolation, snapshot-restore for parallel rollouts, scale-to-zero).
   - **Heavy multi-container Compose repos** (e.g., PostHog-class stacks needing ClickHouse + Kafka + 20+ GB disk or DinD): **`grad env serve`** (`environments.Remote`) first; pre-baked Ephemeral EC2 slots in `gradiated-sandbox-prod` only if managed hosting is required later.

## v0 Scope vs. Deferred Work

### Included in v0
- **Control Plane (`grad-server`):** `Datasets` (`push`, `from_hf`, `BySession` split, `render`), `Runs` (static `plan`, `create`, `resume`, `max_cost_usd`, SSE metrics), `Checkpoints` (30d TTL + `promote`), `Artifacts` (`name@date-n`, download PEFT/merged Safetensors), `Evals` (`Judge` + built-in `validators.*`), `Feedback`.
- **Recipes (6):** `SFTRecipe`, `DPORecipe`, `RouterRecipe`, `DecisionModelRecipe`, `CartridgeRecipe`, `EmbeddingRecipe`.
- **Base Models (initial serving pools):** Start with 2–3 standing LoRA-enabled Qwen3 pools (e.g., `qwen/qwen3-0.6b` or `4b`, `qwen/qwen3-8b`, `qwen/qwen3-32b`) plus `gradiated/linden-1` and `baai/bge-small-en-v1.5` to control standing GPU burn; expand as demand warrants.
- **Serving & Deploy:** Finish `ART-01`/`SERV-01`/`SERV-03` LoRA serving + Cartridge SGLang serving + `/v1/embeddings` + `/v1/route`. Simple `deploy()` / `grad deploy` pointer promotion + manual rollback.
- **SDK & Packaging:** Python `grad-sdk` + `grad` CLI, `grad local up` (Docker Compose), and Helm chart.

### Deferred to Wave 2 / v1+
- **Recipes:** `DistillRecipe`, `RewardModelRecipe`, `GRPORecipe` (typed SDK definitions retained).
- **RL & Sandboxes:** `grad env serve` (`environments.Remote`), colocated SGLang RL rollout engine, AWS Lambda MicroVM `SandboxProvider`, `Harbor`, `verifiers` Hub, `DockerCompose`.
- **Interactive `Trainer` API:** `forward_backward()`, `optim_step()`, `CustomLoss` (`/forward` + `/backward-surrogate`), `trainer.snapshot()`, multi-tenant LoRA multiplexing.
- **Advanced Deploy:** Traffic-splitting `canary`, `shadow` mirroring, automated `rollback_if_quality_drop`.
- **Extra SDKs & Features:** TypeScript/Go/Rust SDKs (generated from OpenAPI once v0 stabilizes), `mergers.*`, GPU-backed 64-prompt `max_new_tokens="auto"` dry-run probing, multimodal `MediaRef`, DeepSeek MoE training.

## v0 Build Sequence

1. **`grad-server` core (Postgres + S3):** Schema, OpenAPI spec, dataset ingestion + `BySession` split + `render`, static `runs.plan()`, checkpoint/artifact registry, local auth + Postgres job queue, and `grad local up` Docker Compose stack.
2. **Upgraded `grad-trainer`:** Extend [autotrain](../product/packages/autotrain/README.md) with sequence packing, pinned chat-template & thinking-aware loss masking, LoRA SFT + DPO, Cartridge (`PrefixKV`), Router, Decision (`linden-1`), and Embedding (`bge-small-en-v1.5`) trainers, token metering, and `max_cost_usd` graceful checkpoints.
3. **Cloud Adapters & Serving Completion:** Wire the 3 Cloud adapters (Auth, Billing, Deploy), deploy `grad-server` to EKS `training` namespace with Temporal + dedicated training GPU pool, finish `ART-01`/`SERV-01` LoRA + Cartridge serving qualification, and add `/v1/route` and `/v1/embeddings`.
4. **Python `grad-sdk`, `grad` CLI & Helm Chart:** End-to-end developer loop (`datasets.push` → `runs.plan` → `runs.create` → `deploy` / `artifacts download`) tested against both `grad local up` and Cloud.
