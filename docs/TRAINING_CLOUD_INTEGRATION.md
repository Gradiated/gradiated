# Training ↔ Cloud integration

- status: design, with the grad side on grad `main` and the product, fleet and infra sides in draft PRs (below)
- related: [TRAINING_PLATFORM_ARCHITECTURE.md](TRAINING_PLATFORM_ARCHITECTURE.md), [DATA_MODEL.md](DATA_MODEL.md), [TASK_FINE_TUNING_SERVING_CONTRACT.md](TASK_FINE_TUNING_SERVING_CONTRACT.md), [virtual-kubelet README](../tools/virtual-kubelet/README.md) (gpu-fleet operator, host leases); in grad: `docs/CLOUD_MODE.md` (every Cloud setting and contract, grad's view), `docs/ARTIFACT_FORMATS.md`, `docs/SELF_HOSTING.md` (worker authentication)
- draft PRs:
  - product (Gradiated/gradiated): [#83](https://github.com/Gradiated/gradiated/pull/83) auth view, [#84](https://github.com/Gradiated/gradiated/pull/84) JWTs, [#86](https://github.com/Gradiated/gradiated/pull/86) price lists and ingest, [#87](https://github.com/Gradiated/gradiated/pull/87) private training listener, [#88](https://github.com/Gradiated/gradiated/pull/88) inference usage plan, [#89](https://github.com/Gradiated/gradiated/pull/89) console, [#90](https://github.com/Gradiated/gradiated/pull/90) publish, [#91](https://github.com/Gradiated/gradiated/pull/91) LoRA rank 32, [#92](https://github.com/Gradiated/gradiated/pull/92) eval-only versions and eval lane, [#93](https://github.com/Gradiated/gradiated/pull/93) model uploads on grad, [#94](https://github.com/Gradiated/gradiated/pull/94) retire the old stack
  - fleet: [#85](https://github.com/Gradiated/gradiated/pull/85) gpu-fleet grad tenancy
  - infra (Gradiated/infrastructure): [#9](https://github.com/Gradiated/infrastructure/pull/9) bucket, KMS, roles, DB bootstrap; [#10](https://github.com/Gradiated/infrastructure/pull/10) secrets and namespace; [#11](https://github.com/Gradiated/infrastructure/pull/11) Argo release, network policies, tailnet console; [#12](https://github.com/Gradiated/infrastructure/pull/12) alerts and dashboard; [#13](https://github.com/Gradiated/infrastructure/pull/13) tailnet ACL

grad (github.com/Gradiated/grad, MIT) is the open-source training platform: `grad-server` (API, Postgres queue, S3), `grad-trainer` and eval workers (pull workers), the Python, TypeScript, Go and Rust SDKs and the CLI. This document defines how Gradiated Cloud runs it next to the product and inference stack.

Names used below:

- **Model** is a product `tasks` row and **Version** a `task_versions` row (`product/packages/control/src/db/schema/training.ts`). Promote is `PUT /api/v1/workspaces/{ws}/tasks/{task}/production`; rollback and history are existing inference features.
- **Product API** is `product/services/api`; **gateway** is `product/services/gateway`; **operator** is `product/services/gpu-fleet`; **host agent** is the virtual-kubelet host agent (`tools/virtual-kubelet`, `product/inference/host`).

## Decisions

- **M1 is import, train, eval, download and deploy.** Deploy means publishing an artifact as a Version and promoting it, for LoRA and cartridge artifacts. Encoder, router, decision and reward bundles follow.
- **Members can train.** Secrets, source writes and deploy are admin-only.
- **US only.** One bucket in us-east-1, no artifact replicas.
- **No scheduled retraining.** `tasks.training_schedule` is not carried over.
- **One set of plan limits** for every customer: grad's defaults (8 running jobs per kind and 500 queued per workspace).
- **Serving pools scale on demand**, with no standing floors. Evals and first requests wait for a cold start.
- **Prices are placeholders** until billing sets real ones.

## 1. Principles

1. **Two planes.** Training (grad-server, its workers, its DB and S3 prefixes) and inference (product API, gateway, GPU pools) have separate deploys, databases and failure domains.
2. **Artifacts are the only boundary.** Inference consumes immutable grad artifacts by reference: no shared job state, no deploy state in grad, no training state in the product.
3. **Neither plane can take the other down.** grad-server is never on an inference request path, inference never waits on training, and GPU sharing always favours inference (§6).
4. **One control plane** owns identity (orgs, workspaces, members, `grad_` keys, JWT signing), billing (balances, price lists, the usage ledger) and the model namespace.
5. **No shared databases**, except one read-only, versioned auth view (`auth_principals_v1`) that grad reads until SDKs exchange keys for JWTs (§3.6).
6. **Same code for OSS and Cloud.** Cloud plugs in through grad's adapters (`server/api/src/cloud/`). The Postgres queue plus pull workers is the only orchestration path; there is no Temporal.

## 2. Artifacts

### 2.1 Ownership and provenance

grad's registry (`grad_artifacts`) owns every servable artifact, whatever its origin. Trained, uploaded and imported artifacts are one primitive with one storage layout, usable for evals, publishing and continued training.

| `provenance.source` | Created by                                                                                                    | Provenance                                |
| ------------------- | ------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| `run`               | A run's final bundle, or a promoted checkpoint                                                                | `run_id`                                  |
| `upload`            | `grad artifacts upload <dir> --base <model>`: presigned upload, then a CPU import job validates and bundles   | `uploader` (the API key)                  |
| `import`            | `grad artifacts import hf://owner/name@rev --base <model>`: a CPU import job downloads, validates and bundles | `uri` (`hf://owner/name@<40-hex commit>`) |

- Manifests are `format_version` 2, which makes `provenance` required in final manifests; readers accept 1 and 2.
- Uploads and imports are checked against ARTIFACT_FORMATS (file set, tensor shapes against the base's `config.json`, no pickle weights, 5 GB cap). A bundle that fails never reaches `artifacts/` (`invalid_artifact`, naming the file).

### 2.2 Storage layout

One bucket, `gradiated-prod-training-<account>` in us-east-1: SSE-KMS with its own key, versioned, TLS-only, private (infra #9).

| Prefix                                  | Holds                                                                                                                                               | Lifetime                                                               |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `artifacts/<ws>/<sha256>`               | Released bundles (trained, promoted, uploaded or imported), content-addressed, with a full-object SHA-256 checksum equal to the artifact's `sha256` | Until deleted; never while pinned. No lifecycle rule.                  |
| `ws/<ws>/jobs/<job>/<attempt>/<sha256>` | Checkpoints and staged import parts                                                                                                                 | Checkpoint retention; `grad-state=staging` objects expire after 2 days |
| `ws/<ws>/datasets/...`                  | Dataset parts (`.jsonl.gz`)                                                                                                                         | Kept                                                                   |
| `uploads/<ws>/<sha256>`                 | Staged dataset files and artifact uploads                                                                                                           | grad sweeps at 7 days, lifecycle at 8                                  |

- **Checkpoints are not servable.** Promoting one is a server-side CopyObject (`ChecksumAlgorithm=SHA256`) into `artifacts/`.
- Every object under `artifacts/` is a single PUT signed with `x-amz-checksum-sha256` or such a copy, so a `HEAD` with `ChecksumMode=ENABLED` returns the SHA-256 and nobody rehashes a bundle.
- Noncurrent versions are kept 30 days, so a bug in the deletion guard is recoverable.

### 2.3 Serving reads artifacts in place

- No copy into a serving bucket. The product API's Pod Identity role gets `s3:GetObject` on `artifacts/*` and `kms:Decrypt`, nothing else on the bucket.
- GPU hosts hold no AWS credentials: the existing adapter-download grant path (`product/packages/control/src/training/downloads.ts`) presigns GETs for them, for that workspace and SHA only (#90).
- The loader opens bundles with the hardened reader rules in ARTIFACT_FORMATS (regular files only, manifest checksums, member and byte caps) and serves the format's config, never the trainer's informational fields.

### 2.4 Resolve and pins

Publishing a Version pins its artifact, and grad never deletes a pinned artifact: not by delete, retention, workspace purge or orphan sweep. Pins reference the artifact with `ON DELETE RESTRICT`. The product calls grad's internal listener with a service JWT (§3.4, scope `artifacts:pin`):

| Call                                                                        | Behaviour                                                                                                                                                                                                                                                                                                                                                                                 |
| --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /internal/v1/workspaces/{ws}/artifacts/{ref}`                          | `{artifact, object, download_url, expires_at}`: the artifact (format, `sha256`, `size_bytes`, base model, manifest, provenance), `object` (`key`, `sha256`, base64 `checksum_sha256`, `checksum_type: FULL_OBJECT`, checked against the store on every call) and a 15-minute presigned GET. `404`; `409 artifact_not_servable` for `reference` bundles; `409 artifact_checksum_mismatch`. |
| `PUT /internal/v1/workspaces/{ws}/artifacts/{id}/pins/{holder}` `{reason?}` | `201`, or `200` if the holder already pins it. `holder` is `inference:version:<task_versions.id>`.                                                                                                                                                                                                                                                                                        |
| `DELETE /internal/v1/workspaces/{ws}/artifacts/{id}/pins/{holder}`          | `204`, also when there was no pin.                                                                                                                                                                                                                                                                                                                                                        |

- `DELETE /v1/artifacts/{id}` on a pinned artifact is `409 artifact_pinned`, naming the holders.
- Pin before Version: the product pins, then inserts the Version; a failed insert unpins. Deleting a Version unpins through a durable outbox (`task_version_pin_releases`, retried every minute). A leaked pin only keeps bytes.

### 2.5 Publishing (deploy)

Publishing and the pin calls are the only new inference features; promote, rollback and history are unchanged. #90 adds:

```
POST /api/v1/workspaces/{ws}/tasks/{task}/versions   (product API, public, Idempotency-Key)
{"artifact": "fast-diff-merge@2026-11-26-1", "name": "2026-11-26-1"}
```

1. Resolve the artifact on grad (§2.4) and read the bundle in place, checking its SHA-256, size and every file against the manifest.
2. Validate it with the existing LoRA and cartridge validators against the pinned base. `peft_lora` and `cartridge` only: `encoder_safetensors`, `router_bundle`, `decision_bundle` and `reward_bundle` answer `422 format_not_servable_yet`. Other errors: `422 format_not_servable | base_revision_mismatch | base_model_not_servable | invalid_artifact | artifact_not_servable`, `409 model_base_mismatch | version_name_taken`.
3. Pin, create the Model on first publish, insert the Version (`adapter.artifact_uri` = the bundle's key, `adapter.source = {kind: "grad", artifact_id, ...}`). Idempotent per (Model, artifact).
4. Qualify on serving capacity as today, without promoting. Promote is a separate call.

- Names default to the artifact's (`fast-diff-merge` / `2026-11-26-1`), served as `<org-slug>/fast-diff-merge`. Publishing into another Model name is allowed; the org-wide uniqueness of `tasks` applies (`409 model_name_taken`).
- Serving's LoRA rank cap rises to 32, grad's default, checked against pool memory (#91).
- Artifact-backed Versions fail closed like cartridges: no base-model or OpenRouter fallback.
- Publishing happens in the console or through the product API. grad has no deploy surface: `/v1/deployments*`, `/v1/route`, `/v1/embeddings`, `/v1/feedback` and every SDK and CLI `deploy` are gone from grad `main`.

### 2.6 Migrating the model-uploads flow (#93)

Today `POST /api/v1/workspaces/{ws}/model-uploads` plus `PUT …/model-uploads/{id}/version` uploads PEFT and cartridge files into the product bucket and creates a Version.

1. `grad artifacts upload` and `import` ship (done in grad).
2. The console's upload page calls grad's upload API, then publishes.
3. `model-uploads` answers `410 use_grad_artifacts_upload` for new uploads (behind a flag); uploads already started complete for 24 h.
4. Backfill: a one-shot job imports every existing Version's files as a grad artifact, pins it and rewrites `adapter.artifact_uri`. Versions keep their ids, names and production pointers.
5. Once no Version references the old prefixes, delete `runs/` and `cartridges/` from the product bucket, the upload routes, `model_uploads` and `upload-store.ts`.

## 3. Auth

### 3.1 Keys and roles

- One control-plane `grad_` key (`api_keys`) works for inference and training. Keys are created and revoked in the console or product API only; grad's `/v1/keys` answers `501 keys_managed_by_cloud` in `AUTH_MODE=cloud`.
- Permissions are role-based, from the key creator's membership (the console token's `role` for console calls):

| Role     | grad scopes                                                                                       |
| -------- | ------------------------------------------------------------------------------------------------- |
| `admin`  | `admin` (every workspace scope)                                                                   |
| `member` | `datasets:read/write`, `runs:read/write` (evals included), `artifacts:read/write`, `sources:read` |

- `api_keys.scopes text[] NULL` (#83): `NULL` or empty is the role's full rights; a non-empty list is intersected with the role. Per-key permissions later are a console feature, not a migration.
- `trainer:worker` and `artifacts:pin` are never customer scopes.

### 3.2 `auth_principals_v1` (#83)

A `security_barrier` view in the product database, owned by the product's migrations, readable only by `grad_auth_reader` (`SELECT` on the view, `CONNECTION LIMIT 10`; the infra bootstrap job creates the role).

| Column                                 | Type          | Notes                                                                                                             |
| -------------------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------- |
| `key_hash`                             | `bytea`       | SHA-256 of the secret (`api_keys.digest`). Lookup key.                                                            |
| `api_key_id`, `workspace_id`, `org_id` | `uuid`        |                                                                                                                   |
| `org_slug`                             | `text`        | Model namespace prefix                                                                                            |
| `user_id`                              | `uuid`        | The key's creator                                                                                                 |
| `actor`                                | `text`        | `key:<api_key_id>`                                                                                                |
| `role`                                 | `text`        | `admin` \| `member`                                                                                               |
| `status`                               | `text`        | `active` only when the org is active, the workspace unarchived and the creator an active member; else `suspended` |
| `scopes`                               | `text[]`      | NULL or empty = the role's rights                                                                                 |
| `expires_at`                           | `timestamptz` | NULL = no expiry                                                                                                  |

- Revoked, expired and hidden keys and non-customer organizations have no row.
- grad: `SELECT … FROM auth_principals_v1 WHERE key_hash = $1`. No row or `expires_at <= now()` → 401; `status <> 'active'` → `403 workspace_suspended`.
- **Cache:** in-process, by token hash, 5 s for hits and misses alike, 10,000 entries LRU; concurrent requests for one key share one query. There is no instant revocation (no LISTEN/NOTIFY, no Redis): revocation and suspension take effect within 5 s.
- Pool: 4 connections per replica, 2 s connect and statement timeouts. Product DB unreachable and the key not cached → `503 auth_unavailable` (fails closed).
- Versioning: columns are only added. A breaking change ships `auth_principals_v2` beside it.

### 3.3 Console JWTs (#84)

The console calls grad's public API with short-lived JWTs from Better Auth's `jwt()` plugin, replacing the hidden per-member training keys (`createHiddenCredential`).

```
POST /api/v1/workspaces/{workspace_id}/training-tokens   (session only; API keys refused)
→ 201 {"token": "<jwt>", "expires_at": "…"}
```

- ES256 with `kid`. Claims: `iss` = `BETTER_AUTH_URL` (`https://api.gradiated.com`), `aud = training`, `sub = user:<user_id>`, `org`, `ws`, `role`, `jti`, `iat`, `exp = iat + 600` (10 minutes).
- JWKS at `GET https://api.gradiated.com/api/auth/jwks`. Keys live in the product DB, rotate every 90 days and stay published 30 days after.
- grad accepts EdDSA, ES256 or RS256 (≥ 2048 bits) with a matching key type, requires `kid`, refuses `crit`, checks `iss`, `aud`, `exp` and `nbf` with 60 s skew, and caches the JWKS 10 minutes (refetched on an unknown `kid` at most every 30 s). No DB read on the JWT path. Bearer only, never cookies.
- Retiring hidden keys: console training pages never mint a hidden key; then the gateway accepts `aud=inference` JWTs for the playground and the OAuth/MCP credential; then `createHiddenCredential` and `api_keys.hidden` go.

### 3.4 Service calls

- **Product → grad:** service JWTs from the same Better Auth key set (`signServiceToken`, #84): `sub = service:<name>` (`service:inference`), `aud = training`, `ws` (must equal the path's), `scopes` (`artifacts:pin` or `workspaces:admin`), `exp = iat + 300`, no `org` or `role`. They're accepted only on grad's `INTERNAL_PORT`, never the public listener, and console tokens are refused there. No shared secret flows product → grad.
- **grad → product:** a private product API listener on port 3005 (#87; `TRAINING_INTERNAL_HOST:TRAINING_INTERNAL_PORT`, ClusterIP `api-training-internal.gradiated.svc:3005`). It starts only when `TRAINING_INTERNAL_TOKEN` (≥ 32 chars) is set and accepts `Authorization: Bearer` with it or `TRAINING_INTERNAL_TOKEN_PREVIOUS` during rotation, with no per-IP limit. grad sends it as `CLOUD_SERVICE_TOKEN`. It is not the unauthenticated GPU-control listener.

### 3.5 Workers

grad accepts three worker credentials (`GRAD_WORKER_AUTH`), tried in order:

| Mode         | Token                                                                                                            | On Cloud                                           |
| ------------ | ---------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `static`     | A key in `TRAINER_KEYS_JSON`, scoped by job kind                                                                 | First release only (infra #11, grad 0.2.0-alpha.3) |
| `kubernetes` | The pod's projected service-account token (audience `grad`), checked with TokenReview; the account maps to kinds | CPU `import` and `eval` workers in EKS             |
| `lease`      | A `gradwt_` token the operator mints per host and lease                                                          | GPU workers on leased fleet hosts (§6)             |

Lease-token contract, on grad's `INTERNAL_PORT` with `Authorization: Bearer <orchestrator key>` (`GRAD_ORCHESTRATOR_KEYS_JSON`, `[{label, sha256, kinds}]`):

```
POST /internal/v1/worker-tokens {"host_id", "lease_id", "kinds": ["train"], "gpu_memory_gb"?, "expires_at"}
→ 201 {"token": "gradwt_…", "host_id", "lease_id", "kinds", "gpu_memory_gb", "expires_at"}   (once; Cache-Control: no-store)
DELETE /internal/v1/worker-tokens/{lease_id} → 200 {"lease_id", "revoked"}                      (own tokens only; idempotent)
```

- `expires_at` is in the future and at most 7 days ahead; `kinds` stay within the orchestrator key's kinds.
- A token is bound to its orchestrator, host and lease together. The worker runs with `GRAD_WORKER_ID=<host_id>` (`403 worker_host_mismatch` otherwise) and can't report more GPU memory than the token allows (`403 gpu_memory_exceeds_token`).
- Rotation re-mints with the same `host_id` and `lease_id` into `GRAD_WORKER_TOKEN_FILE`, which the worker re-reads on every request.
- Lease tokens are checked on every request, never cached, so revoke after the drain takes effect at once.
- TokenReview: only JWTs naming audience `grad`, a mapped account and a future `exp` are reviewed, at most 8 at once per replica (past that `503 worker_auth_unavailable`); positive reviews are cached 60 s at most. grad-server's ClusterRole only creates `tokenreviews`.
- The operator reaches `INTERNAL_PORT` over the private network only.

### 3.6 Later: SDK key → JWT exchange

`POST /api/v1/auth/token {"grant_type": "api_key", "audience": "training"}` with `Authorization: Bearer grad_…` returns the same JWT. SDKs exchange once and refresh before `exp`. When every supported SDK does this, grad stops accepting raw `grad_` keys on Cloud, and the view and `grad_auth_reader` are dropped.

### 3.7 Workspace lifecycle

`PUT /internal/v1/workspaces/{ws}/state {state}` on grad (service JWT, `workspaces:admin`), idempotent, returning `{workspace_id, state, purge_after, purged_at, last_error, updated_at}`; `GET` reads it.

| `state`     | Sent when                                    | grad                                                                                                                                                                                                                                                                                           |
| ----------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `suspended` | Organization suspended or workspace archived | New jobs and resumes `403 workspace_suspended`; queued runs become `stopped_balance`; running runs checkpoint and stop at their next heartbeat (`stopped_balance`, resumable); evals are cancelled; sources pause.                                                                             |
| `active`    | Reinstated                                   | Jobs accepted again; the sources the suspension paused resume; stopped runs wait for a resume.                                                                                                                                                                                                 |
| `deleted`   | Workspace hard-deleted                       | Terminal (`active` afterwards is `409 workspace_deleted`). Runs and evals are cancelled; after 7 days (`GRAD_WORKSPACE_PURGE_DELAY_SECONDS`) grad purges sources, secrets, jobs, datasets, unpinned artifacts and their objects. Pinned artifacts stay until unpinned; the usage ledger stays. |

The auth view already stops new API calls within 5 s; the hook stops running work and owns data deletion.

## 4. Billing

### 4.1 `usage_events`

One ClickHouse table for both planes (#86, `clickhouse/migrations/0003_usage_events.sql`): `ReplacingMergeTree`, partitioned by month, ordered by `(organization_id, workspace_id, event_id)`, inserts with `insert_deduplication_token = event_id`. The money ledger stays `balance_transactions`; `usage_events` records what was billed, for usage views, invoices and Metabase.

Columns: `event_id`, `organization_id`, `workspace_id`, `product` (`inference` | `training`), `sku`, `quantity`, `amount_nano_usd`, `price_version`, `occurred_at`, `subject_id`, `tags`, `ingested_at`.

### 4.2 Price lists

Billing owns every price. Price lists are versioned and immutable (`price_lists`, `price_list_items`); a change inserts a new version, and the current one is the latest with `effective_at <= now()`.

```
GET /api/internal/v1/billing/prices?product=training[&price_version=pv_…]   (port 3005)
→ 200 {"price_version": "pv_…", "product": "training", "effective_at": "…", "placeholder": true,
       "skus": [{"sku": "train:qwen/qwen3-8b", "unit": "token", "price_nano_usd_per_mtok": 400000000}, …]}
   ETag "<price_version>"; 304 on If-None-Match; 404 for an unknown version
```

- The seed `pv_training_2026_11_27_placeholder` has made-up prices (`placeholder: true`).
- `train:<grad catalog id>` SKUs: a fixed price per million tokens; users never see GPU time or spot vs on-demand. On Cloud, grad offers only models with a `train:` SKU.
- `inference:<gateway model>` SKUs, at blended prompt+completion prices, cover grad's bases and the judge and comparison models. grad uses them only for eval estimates and to decide which judges it allows (a judge without one is `422 unknown_judge_model`). Ingest refuses them.
- grad polls every 5 minutes with `If-None-Match` and keeps the last good list. After 24 h without one, new runs and evals get `503 billing_unavailable`.
- A run pins the `price_version` it was created with; its usage bills at that version whatever the list says later.

### 4.3 Ingest

grad pushes its `grad_usage` ledger (append-only, one row per billed increment of a run attempt) to billing:

```
POST /api/internal/v1/billing/usage-events   (port 3005, ≤ 500 events)
{"events": [{"event_id": "training:run-usage:<run_id>:<attempt>:<tokens_through>",
             "workspace_id": "…", "product": "training", "sku": "train:qwen/qwen3-8b",
             "quantity": 1048576, "amount_nano_usd": 419430400, "price_version": "pv_…",
             "occurred_at": "…", "subject_id": "run_…", "tags": {"attempt": "2", "recipe_kind": "sft"}}]}
→ 200 {"accepted": 500, "duplicates": 0}
   422 {"code": "price_mismatch" | "unknown_workspace", "event_id", "message"}; 409 event_conflict
```

- `amount_nano_usd = (quantity × price + 500000) / 1000000` (integer, half up) at the stated version. Any rejection refuses the whole batch.
- Billing posts one `balance_transactions` row per nonzero event (`type = usage`, `source_type = usage_event`, `source_id = event_id`), so replays are free, then inserts into ClickHouse. If ClickHouse fails, the ledger stays committed. The gateway replays non-settlement ledger rows into its Valkey balances, so admission sees training spend with no gateway change.
- Only `billed_by = grad` rows (training) are pushed; eval rows are the gateway's (§5).
- grad's exporter keeps a `(txid, seq)` cursor and reads only rows from transactions older than every open one, so a late commit is never skipped.
- **Ingest down or refusing:** training goes on and usage buffers in grad's ledger. The push retries with backoff (15 s doubling to 5 min) and never drops a row. Alert on `grad_usage_export_lag_seconds` above 15 minutes. Balance checks see only pushed usage; that lag is accepted.

### 4.4 Balance check

```
POST /api/internal/v1/billing/check {"workspace_id": "…", "estimated_amount_nano_usd": 5000000000}
→ 200 {"allowed": true} | {"allowed": false, "reason": "insufficient_balance" | "suspended"}; 404 unknown workspace
```

- At run, eval and resume create (estimate = the plan's cost or the remaining cap): refused or `404` → `403 billing_denied`; billing down → `503 billing_unavailable`. Invoiced accounts are always allowed; prepaid needs `balance ≥ estimate`.
- At every heartbeat of a running run (estimate 0, cached 30 s per workspace): refused → `should_stop: insufficient_balance` → checkpoint, bill, `stopped_balance`, resumable after a top-up. A billing outage never stops running work.

### 4.5 Inference onto `usage_events` (#88)

The inference money path (gateway Valkey balances → settlement → `balance_transactions`) doesn't change. The settlement loop also writes one `usage_events` row per settled generation and priced token type (`event_id = inference:gen:<id>:<type>`, tags including `lane=eval`); then backfill, move the usage API, console usage pages, Metabase and invoices onto `usage_events`, and reconcile daily against `balance_transactions` for a month. `generations` stays the gateway's raw table.

## 5. Evals on Cloud

Evals are a grad job kind run by CPU eval workers. On Cloud their model and judge calls go through the gateway's eval lane (#92):

```
POST {GRAD_CLOUD_GATEWAY_URL}/chat/completions
Authorization: Bearer <GRAD_CLOUD_GATEWAY_TOKEN>
X-Gradiated-Workspace: <workspace id>
X-Gradiated-Source: eval
X-Gradiated-Eval-Id: ev_…
```

- **Credential.** One gateway service credential (`GATEWAY_EVAL_SERVICE_TOKENS` on the gateway, two values while rotating, compared as SHA-256 in constant time). It is not an `api_keys` row, is accepted only with `X-Gradiated-Source: eval` (else 401) and bills the workspace in `X-Gradiated-Workspace` (missing or unknown → 400). Only grad's eval worker pods hold it, and every use is audit-logged.
- **Lane.** Runtime priority below every service tier; its own per-workspace limit (20 in flight, 600 per minute) before the organization's admission; a full lane answers `429 eval_lane_limited` with `Retry-After: 5`. grad retries 408, 425, 429 and 5xx six times, backing off from 1 s.
- **Eval-only versions.** To evaluate an artifact, grad calls `POST /api/internal/v1/training/eval-versions {workspace_id, artifact_id: "name@version"}` once per artifact target at eval create → `{model: "<org_slug>/grad-eval-<ws>/<name>.<version>", version_id}`. The Version lives in a hidden per-workspace Model, is never listed or promotable, is callable only from the eval lane, and is deleted and unpinned 7 days after its last eval call. It is `available` at once, with no serving probe. A refusal (409/422) is `422 artifact_not_servable` with the product's detail; unreachable → `503 inference_unavailable`. Catalog models are called by their ids.
- **Billed once.** The gateway bills model and judge tokens as normal generations tagged `lane=eval, eval_id`. grad records its eval usage rows with `billed_by = gateway`, shows them in `/v1/usage` and never pushes them.

## 6. GPU sharing (#85)

Training is a preemptible tenant of the existing gpu-fleet: no training pool, no pool controller, no separate account.

### 6.1 Behaviour

- **Lease on demand.** The operator reads `grad_jobs_open{kind="train"}` from Prometheus (each v0 job needs one 80 GB-class GPU). When demand exceeds the GPUs grad holds for 2 minutes, it requests one spare host for holder `grad` (preemptible, 24 h): in the pool, Ready, no pods, an eligible product, enough GPU memory, no pending replica that would land there, and `GRAD_BUFFER_GPUS` left free on the product's other hosts. One grad lease in flight at a time, up to `GRAD_MAX_HOSTS`. No metric samples means grad is down, not idle: current leases are held.
- **Wipe on every switch.** Lease start re-images the host before trainers start; return re-images it again. A host never serves and trains at once, and the host agent enforces that too.
- **Trainers.** The operator mints a lease token (§3.5, kind `train`, bound to the host and lease, expiring with it) and calls the host agent's `train_start`, which starts one worker per GPU from the `grad-trainer` bundle pinned in `runtimes.json` with `GRAD_SERVER_URL`, `GRAD_WORKER_TOKEN_FILE` and `GRAD_WORKER_ID=<host_id>`.
- **Inference first.** A model replica with no node reclaims a grad host it fits 30 s after the last rollout settled (a person's lease waits 10 minutes). The operator sends `train_stop`; workers checkpoint if they can within `GRAD_RECLAIM_GRACE_SECONDS`, complete their attempt as `compute_reclaimed` (billed, requeued at once, not counted toward `MAX_ATTEMPTS`) and exit; SIGKILL after `GRAD_DRAIN_GRACE_SECONDS` (90). Then the token is revoked and the host re-imaged and returned.
- **Scale down.** A grad host whose GPUs demand hasn't needed for 15 minutes is returned the same way.

### 6.2 Operator and host agent

- Operator config: `GRAD_ENABLED` (default `false`), `GRAD_BUFFER_GPUS`, `GRAD_MAX_HOSTS`, `GRAD_GPU_PRODUCTS`, `GRAD_DRAIN_GRACE_SECONDS`, `GRAD_PROMETHEUS_URL`, `GRAD_INTERNAL_URL`, `GRAD_SERVER_URL`, `GRAD_ORCHESTRATOR_KEY_FILE`, `GRAD_TRAINER_RUNTIME`. Metrics `gradiated_gpu_fleet_grad_{demand_jobs,gpus,events_total}`.
- Host agent: `train_start`, `train_stop`, `train_status`, guarded by the management key. `train_start` refuses while any pod state, pod process or GPU compute process exists; pod creation is refused while trainers run.
- Remove the `gpu-training` PriorityClass and training-Job handling once §10 is done.

grad needed nothing else: lease tokens, pull workers, heartbeats, `compute_reclaimed` requeue, checkpoint-on-SIGTERM and GPU-fit claiming are on grad `main`.

## 7. Console (#89)

- Training pages live in the product console behind the `grad-training` flag and call grad's public API through the TypeScript SDK with the §3.3 JWT, renewed a minute before expiry and once after a 401.
- grad allows the console origin by CORS (`GRAD_CORS_ORIGINS`, exact origins, bearer only, no cookies). Live progress reads grad's SSE stream with `fetch` (EventSource can't send `Authorization`) and resumes with `Last-Event-ID`.
- Downloads use `GET /v1/artifacts/{id}/download-url` (`artifacts:read`), a 15-minute presigned GET, so browsers stream from storage instead of through the API.
- Uploads go from the browser straight to S3 with the ticket's presigned PUT and headers. The bucket needs a CORS rule for the console origin: methods PUT, GET, HEAD; headers `content-type`, `content-length`, `x-amz-checksum-sha256`, `x-amz-sdk-checksum-algorithm`, `x-amz-tagging`; expose `ETag`; max age 600.
- Deploy publishes through §2.5, admins only, LoRA and cartridge only. Members can start runs.
- The console never reads grad's database. Business rules, tenant scoping, schema churn, idempotent writes and the SSE event hub all live in grad. Cross-plane reporting reads ClickHouse `usage_events`.
- grad's own web UI is for staff: on the tailnet (`http://grad.tail186117.ts.net/`, infra #11 and #13), never the public ALB.

## 8. Deployment

| Item           | Value                                                                                                                                                                                                                                                                                                                                                                                  |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Namespace      | `training` in the prod EKS cluster (us-east-1); Argo CD Application from grad's chart, vendored in infra (#11)                                                                                                                                                                                                                                                                         |
| grad-server    | 2 replicas, `AUTH_MODE=cloud`, `BILLING_MODE=cloud`; public listener `:8787` (customer API) and `INTERNAL_PORT` (ClusterIP only: lease tokens, workspace hooks, resolve and pins)                                                                                                                                                                                                      |
| Workers in EKS | CPU `import` pool (file and artifact imports, source syncs; the only pods with workspace secrets) plus eval workers; `kubernetes` worker auth; KEDA on `grad_jobs_open`, `import` min 1                                                                                                                                                                                                |
| GPU workers    | Leased fleet hosts only (§6), with lease tokens; none in EKS                                                                                                                                                                                                                                                                                                                           |
| Database       | Logical database `grad` on the existing `gradiated-prod` RDS (Postgres 17), owner `grad_server`; `grad_auth_reader` in `gradiated` with `SELECT` on `auth_principals_v1` only; `sslmode=verify-full` (#9)                                                                                                                                                                              |
| S3             | §2.2; one bucket, no replicas                                                                                                                                                                                                                                                                                                                                                          |
| AWS identity   | Pod Identity. grad-server: read/write on the bucket and its KMS keys (secrets on KMS via `GRAD_SECRETS_KMS_KEY_ID`). Product API: `s3:GetObject` on `artifacts/*`, `kms:Decrypt`. Workers: none (presigned URLs only).                                                                                                                                                                 |
| Secrets        | `gradiated/prod/training/grad-server` (DB passwords, `GRAD_SECRETS_KEY`, `CLOUD_SERVICE_TOKEN`, worker key, orchestrator key hash) and `gradiated/prod/training/grad-config`, through a training-only External Secrets role (#10). Product API: `TRAINING_INTERNAL_TOKEN`. Gateway: `GATEWAY_EVAL_SERVICE_TOKENS` = grad's `GRAD_CLOUD_GATEWAY_TOKEN`. Operator: the orchestrator key. |
| ALB routes     | Later: `api.gradiated.com` `/v1/{datasets,runs,checkpoints,artifacts,artifact-imports,evals,imports,uploads,sources,secrets,base-models,usage}` → grad-server `:8787`. Never `/v1/keys`, `/v1/trainer-jobs` or `/internal`.                                                                                                                                                            |
| Monitoring     | grad's alerts and dashboard (#12), plus export lag and the operator's grad metrics                                                                                                                                                                                                                                                                                                     |

The first release (#9–#13) is smaller: grad 0.2.0-alpha.3 with a static worker key, `BILLING_MODE=noop`, no GPU workers, no evals and no public route. Cloud auth, billing and evals switch on with a grad release that has them.

Network policies (default deny in `training`; enforced once the VPC CNI policy agent is on):

| From                       | To                                                        | Why                                                |
| -------------------------- | --------------------------------------------------------- | -------------------------------------------------- |
| ALB                        | grad-server `:8787`                                       | Customer API, console                              |
| Product API (`gradiated`)  | grad-server `INTERNAL_PORT`                               | Resolve, pins, workspace hooks                     |
| gpu-fleet operator         | grad-server `INTERNAL_PORT`                               | Lease tokens                                       |
| Leased GPU hosts (tailnet) | grad-server `:8787` (`/v1/trainer-jobs/*`)                | Worker protocol                                    |
| `import` and eval workers  | grad-server `:8787`                                       | Worker protocol                                    |
| Eval workers               | gateway                                                   | Eval lane                                          |
| `import` workers           | public `:443` except private, CGNAT and link-local ranges | Providers, HF Hub (SSRF guard)                     |
| grad-server                | RDS, product API `:3005`, JWKS, S3, KMS, DNS              | DB, auth view, billing, prices, eval-only versions |
| Prometheus                 | grad-server metrics                                       | KEDA and the operator's demand metric              |

Nothing in `gradiated` or `gpu-inference` calls grad on a request path; the gateway has no route to grad.

## 9. Failure matrix

| Down                   | Still works                                                                    | Stops or degrades                                                                                                         |
| ---------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| grad-server or grad DB | All inference, including published Versions, promote and rollback              | Training API and console training pages; new publishes (resolve, pin); workers retry, then leases expire and jobs requeue |
| Product DB (auth view) | Running jobs; console JWT calls (JWKS cached); keys cached < 5 s               | Other key calls `503 auth_unavailable`; balance checks, so new jobs `503`; inference itself                               |
| Product API            | Running jobs (a billing outage never stops them); cached keys; prices for 24 h | Console tokens, new jobs (balance check), usage push (buffers in `grad_usage`), eval-only versions, publish               |
| Gateway                | Training, imports, downloads                                                   | Evals (retried, then failed); all inference                                                                               |
| ClickHouse             | Training, inference, balances (ingest commits the ledger first)                | Usage views go stale                                                                                                      |
| S3                     | Inference with adapters already loaded                                         | Everything that moves bytes                                                                                               |
| gpu-fleet operator     | Running training on leased hosts; serving                                      | No new grad leases and no reclaim until it recovers (alerted)                                                             |
| Prometheus             | Running jobs; reclaim (driven by pending pods)                                 | No new grad leases (held as they are); KEDA keeps current replicas                                                        |
| A leased GPU host      | Everything else                                                                | Its jobs requeue after lease expiry (`worker_lost`)                                                                       |

## 10. Retiring the old training stack (#94)

The old stack: Temporal workflows in `product/services/temporal-worker/src/training` (the only Temporal user) and `packages/temporal`; training Kubernetes Jobs on virtual-kubelet nodes (`gpu-training` PriorityClass, `kubernetes-host.ts`, training runtimes in `runtimes.json`); `training_runs`, `training_run_events` and `tasks.training_schedule`; the model-uploads path and the product bucket's `runs/` and `cartridges/` prefixes.

1. grad on Cloud reaches M1; console training pages switch to grad.
2. Flag off new product training runs and schedules (scheduled retraining is not replaced); let in-flight Temporal runs finish or cancel them.
3. Backfill existing Versions into grad artifacts (§2.6 step 4). Export `training_runs` and `training_run_events` to S3 for audit.
4. Remove the Temporal training workflows and worker, the `temporal-worker` Deployment and its secrets, then the Temporal Cloud namespace.
5. Remove training Jobs from virtual-kubelet and the host agent, the `gpu-training` PriorityClass and training runtimes.
6. Switch model-uploads to `410`, then remove its routes and tables (§2.6 step 5).
7. Drop `training_runs`, `training_run_events`, `model_uploads` and the unused `tasks` training columns.

## 11. Work breakdown

**M1:** import, train, eval, download and deploy (LoRA and cartridge). **M2:** encoder, router, decision and reward serving, gateway feedback and the `gradiated` source.

### grad repo (on `main`)

| #   | M   | Task                                                                                                           | State            |
| --- | --- | -------------------------------------------------------------------------------------------------------------- | ---------------- |
| G1  | 1   | Drop deployments, route, embeddings and feedback from server, spec, SDKs and CLI; `/v1/keys` 501 in cloud mode | done             |
| G2  | 1   | Cloud auth: view reader (5 s cache), JWT verifier, role → scopes                                               | done             |
| G3  | 1   | `INTERNAL_PORT` listener for lease tokens, workspace hooks, resolve and pins                                   | done             |
| G4  | 1   | Billing: price-list client, integer amounts, xid8 exporter, balance check; eval rows `billed_by = gateway`     | done             |
| G5  | 1   | `artifacts/<ws>/<sha256>` with full-object checksums, provenance, pins, deletion guard, download URLs          | done             |
| G6  | 1   | `grad artifacts upload` and `import hf://` in the CLI and all four SDKs                                        | done             |
| G7  | 1   | Worker auth: static, kubernetes TokenReview, lease tokens; security review fixes                               | done             |
| G8  | 1   | Gateway evals and eval-only versions                                                                           | done             |
| G9  | 1   | Workspace state hook, CORS, secrets on KMS                                                                     | done             |
| G10 | 2   | `gradiated` source provider over `training/traces:pull`                                                        | done (grad side) |

### product repo

| #   | M   | Task                                                                                                                                                       | PR         |
| --- | --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| P1  | 1   | `api_keys.scopes`, `auth_principals_v1`                                                                                                                    | #83        |
| P2  | 1   | Better Auth `jwt()`, JWKS, training tokens, service JWTs                                                                                                   | #84        |
| P3  | 1   | Price lists (placeholder, `train:` and `inference:` SKUs), balance check, usage ingest → `balance_transactions` + `usage_events`; private listener `:3005` | #86, #87   |
| P4  | 1   | Publish from artifact (LoRA, cartridge), pins and unpin outbox, grants for `artifacts/`, no base fallback; rank cap 32                                     | #90, #91   |
| P5  | 1   | Eval-only versions; gateway eval lane                                                                                                                      | #92        |
| P6  | 1   | Console training pages on the TS SDK with JWTs, including deploy                                                                                           | #89        |
| P7  | 1   | Workspace suspend, reinstate and delete hooks to grad                                                                                                      |            |
| P8  | 1   | Model uploads on grad artifacts: upload page, `410`, backfill                                                                                              | #93        |
| P9  | 2   | Serving for `encoder_safetensors`, `router_bundle`, `decision_bundle`, `reward_bundle`                                                                     |            |
| P10 | 2   | Gateway feedback → ClickHouse with traces; `training/traces:pull` with the late-score watermark                                                            |            |
| P11 | 2   | `usage_events` for inference; hidden-key retirement                                                                                                        | #88 (plan) |
| P12 | 2   | Retire the old training stack                                                                                                                              | #94 (plan) |

### infra and fleet

| #   | M   | Task                                                                                                       | PR             |
| --- | --- | ---------------------------------------------------------------------------------------------------------- | -------------- |
| I1  | 1   | Bucket, KMS, lifecycle rules, Pod Identity roles, DB bootstrap (`grad`, `grad_server`, `grad_auth_reader`) | infra #9       |
| I2  | 1   | Secrets, training-only External Secrets role, namespace                                                    | infra #10      |
| I3  | 1   | Argo release, KEDA, network policies, staff console on the tailnet                                         | infra #11, #13 |
| I4  | 1   | Alerts and dashboard                                                                                       | infra #12      |
| I5  | 1   | VPC CNI network policy on, cluster-wide                                                                    |                |
| I6  | 1   | Operator and host agent grad tenancy, `grad-trainer` bundle pin; `MODE=observe` first                      | #85            |
| I7  | 1   | Qwen3 LoRA pools at grad's pinned revisions, scaling on demand                                             |                |
| I8  | 1   | Public ALB routes for the training API                                                                     |                |

## Open items

1. **No pool serves grad's bases.** Today's LoRA pools are GLM-5.3 Flash and DeepSeek V4.1 Flash; grad trains Qwen3. Until a Qwen3 LoRA pool exists (I7), every grad artifact gets `base_model_not_servable`, for evals and deploys alike.
2. **Evals against pools scaled to zero.** Pools scale on `model_busy_slots`, and eval traffic must not count as demand, so a cold pool never wakes for an eval. Either eval-lane requests wake a pool, or evals wait for other traffic (#92).
3. **Per-workspace scoping of worker tokens** is deferred until tenant code runs on workers. Today a lease token can claim any workspace's `train` jobs, and the gateway credential can spend in any workspace; both stay inside `training` and the fleet.
4. **Artifact key.** grad writes `artifacts/<ws>/<sha256>`; #90 builds `artifacts/<ws>/<sha256>.grad.tar.gz` for reads and grants. #90 should use the resolve's `object.key`.
