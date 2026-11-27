# Training Platform Architecture & v0 Plan

- status: proposed architecture & v0 scoping authority
- date: 2026-11-26
- related: [TRAINING_CLOUD_INTEGRATION.md](TRAINING_CLOUD_INTEGRATION.md) (Cloud integration; supersedes this document where they differ), [ARCHITECTURE.md](ARCHITECTURE.md), [TASK_FINE_TUNING_FLEET_CONTRACT.md](TASK_FINE_TUNING_FLEET_CONTRACT.md), [TASK_FINE_TUNING_SERVING_CONTRACT.md](TASK_FINE_TUNING_SERVING_CONTRACT.md), [CARTRIDGE_SERVING_PLAN.md](CARTRIDGE_SERVING_PLAN.md), [AWS_GPU_PROVIDER_PLAN.md](AWS_GPU_PROVIDER_PLAN.md)

This document defines how the Gradiated training platform (`grad-server`, `grad-trainer`, and the `grad` SDK/CLI) fits alongside our existing production inference stack, how it stays self-hostable from day one, how training compute and sandboxes are isolated, and what is scoped into v0 versus deferred.

## Core Decisions

1. **Portable `grad-server` core (Postgres + S3 only):** The training control plane runs as its own service in a dedicated EKS namespace (`training`) with its own Postgres database (a logical database on the shared RDS) and S3 bucket. It never imports Valkey, ClickHouse, or Better Auth internals directly. Cloud capabilities (auth, token billing and prices, eval inference, sources) plug in through narrow adapters so `grad local up` (Docker Compose), the self-hosted Helm chart, and Gradiated Cloud run the exact same codebase.
2. **LoRA & Cartridges only for LLMs (no `adapters.Full()`):** Every LLM training run produces a small adapter (`LoRA`) or `PrefixKV` Cartridge (~100–300 MB trainable state). This enables multi-tenant parallel LoRA training on shared base weights, compact S3 checkpoints, and guaranteed hot-loading onto shared SGLang serving pools via `ART-01`/`SERV-01`. `EmbeddingRecipe` (`baai/bge-small-en-v1.5`, 33M params) trains its full encoder weights internally.
3. **Per-token billing:** All v0 recipes are offline and throughput-deterministic, billed per million tokens processed (matching inference billing and enabling accurate `runs.plan()` cost estimates).
4. **Deploy, route and feedback are inference-side:** Artifacts are the only boundary. grad-server keeps no deployments, deploy stubs or feedback. The SDKs' `deploy()` / `grad deploy` call the product API, which publishes a Version from the artifact (pinning it) and uses the existing qualification, promote and rollback; `route`, `embeddings` and `feedback` call the gateway. No canaries, shadowing or automated rollback in v0. See [TRAINING_CLOUD_INTEGRATION.md](TRAINING_CLOUD_INTEGRATION.md#2-artifacts).
5. **GPU sharing, plus sandbox isolation:** Training is a preemptible tenant of the gpu-fleet: the operator leases spare serving hosts to grad, inference reclaims them immediately with a graceful drain, and a host is never serving and training at once and is wiped on every switch ([§6](TRAINING_CLOUD_INTEGRATION.md#6-gpu-sharing)). Trainer hosts get only a per-lease train-only key, no AWS or DB credentials. Untrusted customer code/environments (post-v0) run in a separate sandbox AWS account via AWS Lambda MicroVMs behind the same rollout-worker protocol as `grad env serve`.
6. **v0 recipe scope:** Ship `SFTRecipe`, `DPORecipe`, `RouterRecipe`, `DecisionModelRecipe`, `CartridgeRecipe`, `EmbeddingRecipe`, `DistillRecipe` and `RewardModelRecipe` in v0, single-GPU only (no FSDP/DeepSpeed): every catalog base trains on one 80 GB GPU. Keep typed SDK definitions for `GRPORecipe` and `Environment` so the SDK contract does not break when Wave 2 lands.
7. **One orchestration path, no Temporal:** Cloud and self-hosted both use the Postgres `SKIP LOCKED` queue with pull workers scaled by KEDA.
8. **License:** grad is MIT-licensed.

## System Topology

```text
                       ┌───────────────────────────────────────────────┐
                       │   grad-server (EKS `training` namespace)      │
                       │   Own Postgres DB · Own S3 bucket             │
                       │   (Same image ships in Docker Compose / Helm) │
                       └───────┬──────────────────────────┬────────────┘
                               │                          │
           Cloud adapters (narrow HTTP bridges)           │
           • Auth: auth_principals_v1 view + console JWTs │
           • Billing: prices, balance check, usage push   │
           • Artifacts: serving reads artifacts/ in S3    │
                               │                          │
     ┌─────────────────────────▼───────┐      ┌───────────▼─────────────────────────┐
     │  SERVING PLANE (Existing)       │      │  TRAINING PLANE                     │
     │                                 │      │                                     │
     │  • `api` + `worker` (EKS)       │      │  • Orchestration (Cloud and OSS):   │
     │  • Rust `gateway` + Valkey      │      │    PG queue + pull workers (KEDA)   │
     │  • Production SGLang Pool       │      │  • GPUs: spare gpu-fleet hosts      │
     │    (RunPod + gradiated-gpu-prod)│      │    leased to grad, preemptible      │
     │  • Host-owned loader (SERV-01)  │      │    by inference                     │
     │    LoRA + Cartridges + SystemOne│      │  • `grad-trainer` container         │
     └─────────────────────────────────┘      └──────────────────▲──────────────────┘
                                                                 │
                                              Post-v0 RL Rollout Worker Protocol
                                              • v0/v1: `grad env serve` (user laptop/VM)
                                              • v1: AWS Lambda MicroVMs (gradiated-sandbox-prod)
                                              • v2: Pre-baked Ephemeral EC2 (heavy Compose repos)
```

## Service Boundaries & Self-Hosting Parity

`grad-server` owns `datasets`, `runs`, `checkpoints`, `artifacts`, `evals` and `sources` inside its own Postgres database and S3 bucket. Because it has its own DB credentials, it cannot join against Cloud tables (`organizations`, `api_keys`, `balance_transactions`, `model_deployments`); its only read of the product database is the `auth_principals_v1` view.

| Adapter               | Self-Hosted (`grad local up` / Helm)                                     | Gradiated Cloud                                                                                                 |
| :-------------------- | :----------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------- |
| **Auth**              | Local `ADMIN_API_KEY_HASH`, Postgres scoped keys, optional OIDC JWT      | Control-plane `grad_` keys read from the `auth_principals_v1` view (cached 15 s); console JWTs (`aud=training`) |
| **Job Scheduler**     | Postgres `SKIP LOCKED` job queue + pull workers (KEDA scale-to-zero)     | Same queue; CPU workers in EKS, GPU workers on gpu-fleet hosts leased to grad                                   |
| **Metrics & Billing** | `grad_usage` ledger; billing is a no-op                                  | Billing-owned price list; `grad_usage` pushed to `usage_events` ingest; balance check and stop-on-balance       |
| **Artifact Deploy**   | Download the artifact and serve it yourself; the SDK's `deploy()` errors | SDK `deploy()` calls the product API: publish from artifact (pins it), then the existing promote                |

CI runs integration tests against the **self-hosted (Postgres + S3 only)** mode on every PR so Cloud remains strictly an additive layer.

## Isolation Boundaries

1. **Serving vs. Training Compute (GPU sharing):**
   - Superseded by GPU sharing ([TRAINING_CLOUD_INTEGRATION.md §6](TRAINING_CLOUD_INTEGRATION.md#6-gpu-sharing)): serving and training never share a host at once, and a host is wiped on every switch.
   - Training hosts receive no Postgres, Valkey, AWS or provider credentials, only a per-lease train-only key, short-lived presigned S3 grants and the Tailscale route to grad's worker listener.
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

- **Control Plane (`grad-server`):** `Datasets` (`push`, `from_hf`, `BySession` split, `render`), `Runs` (static `plan`, `create`, `resume`, `max_cost_usd`, SSE metrics), `Checkpoints` (30d TTL + `promote`), `Artifacts` (`name@date-n`, download PEFT/merged Safetensors), `Evals` (`Judge` + built-in `validators.*`), `Sources`. Feedback lives in the user's observability tool or, on Cloud, the gateway.
- **Recipes (8, single-GPU):** `SFTRecipe`, `DPORecipe`, `RouterRecipe`, `DecisionModelRecipe`, `CartridgeRecipe`, `EmbeddingRecipe`, `DistillRecipe`, `RewardModelRecipe`.
- **Base Models (initial serving pools):** Start with 2–3 standing LoRA-enabled Qwen3 pools (e.g., `qwen/qwen3-0.6b` or `4b`, `qwen/qwen3-8b`, `qwen/qwen3-32b`) plus `gradiated/linden-1` and `baai/bge-small-en-v1.5` to control standing GPU burn; expand as demand warrants.
- **Serving & Deploy (inference side):** Publish from artifact, LoRA + Cartridge serving, `/v1/embeddings`, `/v1/route`; `deploy()` / `grad deploy` call the product API; promote and rollback are existing features.
- **SDK & Packaging:** Python, TypeScript, Go and Rust SDKs at full parity (generated from OpenAPI) + `grad` CLI, `grad local up` (Docker Compose), and Helm chart.

### Deferred to Wave 2 / v1+

- **Recipes:** `GRPORecipe` (typed SDK definitions retained); multi-GPU training.
- **RL & Sandboxes:** `grad env serve` (`environments.Remote`), colocated SGLang RL rollout engine, AWS Lambda MicroVM `SandboxProvider`, `Harbor`, `verifiers` Hub, `DockerCompose`.
- **Interactive `Trainer` API:** `forward_backward()`, `optim_step()`, `CustomLoss` (`/forward` + `/backward-surrogate`), `trainer.snapshot()`, multi-tenant LoRA multiplexing.
- **Advanced Deploy:** Traffic-splitting `canary`, `shadow` mirroring, automated `rollback_if_quality_drop`.
- **Extra Features:** `mergers.*`, GPU-backed 64-prompt `max_new_tokens="auto"` dry-run probing, multimodal `MediaRef`, DeepSeek MoE training.

## v0 Build Sequence

1. **`grad-server` core (Postgres + S3):** Schema, OpenAPI spec, dataset ingestion + `BySession` split + `render`, static `runs.plan()`, checkpoint/artifact registry, local auth + Postgres job queue, and `grad local up` Docker Compose stack.
2. **Upgraded `grad-trainer`:** Extend [autotrain](../product/packages/autotrain/README.md) with sequence packing, pinned chat-template & thinking-aware loss masking, LoRA SFT + DPO, Cartridge (`PrefixKV`), Router, Decision (`linden-1`), and Embedding (`bge-small-en-v1.5`) trainers, token metering, and `max_cost_usd` graceful checkpoints.
3. **Cloud integration:** Follow the work breakdown in [TRAINING_CLOUD_INTEGRATION.md](TRAINING_CLOUD_INTEGRATION.md#11-work-breakdown): auth view and JWTs, billing ingest, artifacts and pins, Cloud evals, gpu-fleet leases to grad, and `grad-server` in the EKS `training` namespace.
4. **SDKs, `grad` CLI & Helm Chart:** End-to-end developer loop in all four SDKs (`datasets.push` → `runs.plan` → `runs.create` → `deploy` / `artifacts download`) tested against both `grad local up` and Cloud.
