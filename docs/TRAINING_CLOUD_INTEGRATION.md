# Training ↔ Cloud integration

- status: design; the contract product, infra and grad work is split from
- related: [TRAINING_PLATFORM_ARCHITECTURE.md](TRAINING_PLATFORM_ARCHITECTURE.md), [DATA_MODEL.md](DATA_MODEL.md), [TASK_FINE_TUNING_SERVING_CONTRACT.md](TASK_FINE_TUNING_SERVING_CONTRACT.md), [virtual-kubelet README](../tools/virtual-kubelet/README.md) (gpu-fleet operator, host leases), grad's `docs/ARTIFACT_FORMATS.md`

grad (github.com/Gradiated/grad, MIT) is the open-source training platform: `grad-server` (API, Postgres queue, S3), `grad-trainer` (pull workers) and the Python, TypeScript, Go and Rust SDKs plus the CLI. This document defines how Gradiated Cloud runs it next to the product and inference stack: the artifact boundary, auth, billing, evals, GPU sharing, the console, deployment, failure behaviour, retirement of the old training stack, and the work breakdown.

Names used below:

- **Model** is a product `tasks` row and **Version** a `task_versions` row (`product/packages/control/src/db/schema/training.ts`). Promote is `PUT /api/v1/workspaces/{ws}/tasks/{task}/production`; rollback and history are the existing inference features.
- **Product API** is `product/services/api`; **gateway** is `product/services/gateway`; **operator** is `product/services/gpu-fleet`; **host agent** is the virtual-kubelet host agent (`tools/virtual-kubelet`, `product/inference/host`).

## 1. Principles

1. **Two planes.** Training (grad-server, its workers, its DB and S3 prefixes) and inference (product API, gateway, GPU pools) are separate planes with separate deploys, databases and failure domains.
2. **Artifacts are the only boundary.** Inference consumes immutable grad artifacts by reference. Nothing else crosses: no shared job state, no deploy state in grad, no training state in the product.
3. **Neither plane can take the other down.** grad-server is never on an inference request path. Inference never waits on training. GPU sharing always favours inference (§6).
4. **One control plane** owns identity (orgs, workspaces, members, `grad_` keys, JWT signing), billing (balances, the price list, the usage ledger) and the model namespace.
5. **No shared databases**, except one read-only, versioned auth view (`auth_principals_v1`) that grad reads until SDKs exchange keys for JWTs (§3.5). Everything else crosses over HTTP contracts in this document.
6. **Same code for OSS and Cloud.** Cloud plugs in through grad's adapters (auth, billing, prices, eval inference, sources). The Postgres queue plus pull workers is the only orchestration path; Temporal is not used.

## 2. Artifacts

### 2.1 Ownership and provenance

grad's artifact registry (`grad_artifacts`) owns every servable artifact, whatever its origin. Trained and uploaded artifacts are one primitive with one storage layout.

| `source` | Created by                                                                                           | Provenance in the manifest                   |
| -------- | ---------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| `run`    | A run's final bundle, or a promoted checkpoint                                                       | `run_id`, `attempt`, `step`, dataset version |
| `upload` | `grad artifacts upload <dir>`: presigned staging upload, then a CPU import job validates and bundles | `uploaded_by` (actor), original file names   |
| `import` | `grad artifacts import hf://org/repo@rev`: a CPU import job downloads, validates and bundles         | `hf_repo`, `hf_revision`                     |

- Manifests gain `source: run | upload | import` and a `provenance` object with the fields above (additive to `grad.artifact/1`; no `format_version` bump).
- Uploads and imports are validated against `docs/ARTIFACT_FORMATS.md` and `spec/artifacts/*.schema.json` by the same hardened reader the trainer uses, plus base-model shape checks (rank, target modules, hidden size against the pinned base revision). A bundle that fails never reaches `artifacts/`.
- Every artifact, whatever its source, can be evaluated, published and used as the base for continued training.

### 2.2 Storage layout

One bucket, `gradiated-prod-training-<account>`, KMS-encrypted, versioned, TLS-only, private.

| Prefix                                                                  | Holds                                                    | Mutability                            | Who reads it                                |
| ----------------------------------------------------------------------- | -------------------------------------------------------- | ------------------------------------- | ------------------------------------------- |
| `artifacts/<workspace_id>/<sha256>.grad.tar.gz`                         | Released artifacts only (`source` run, upload or import) | Immutable, content-addressed          | grad-server; serving (read-only role, §2.3) |
| `ws/<workspace_id>/jobs/<job_id>/<attempt>/<sha256>`                    | Checkpoints and worker uploads                           | Immutable; uncommitted objects expire | grad-server, the job's worker (presigned)   |
| `ws/<workspace_id>/uploads/<upload_id>/<file>`                          | `grad artifacts upload` staging                          | Uncommitted objects expire            | grad-server, import workers (presigned)     |
| `ws/<workspace_id>/datasets/<dataset_id>/parts/<seq>-<sha256>.jsonl.gz` | Dataset parts                                            | Immutable                             | grad-server, workers (presigned)            |

- **Staging expiry.** Presigned PUTs bind `x-amz-tagging: grad-state=staging`; a lifecycle rule expires that tag after 2 days, and commit removes the tag (`PutObjectTagging`, no copy). Lifecycle filters cannot wildcard `ws/*/`, hence the tag.
- **Checkpoints are not servable.** They stay under their job prefix. Promoting one copies its bundle (server-side multipart `CopyObject`) to `artifacts/` as a `release`; only then can it be published.
- An artifact's storage key is derived from `(workspace_id, sha256)`, so serving never needs a key from grad and cannot be pointed outside the prefix.
- **Regional pools** read a replica: S3 replication of `artifacts/` only, to one bucket per serving region. The serving grant issuer uses the region's replica and falls back to the source bucket while replication is pending (`HeadObject` miss).

### 2.3 Serving reads artifacts in place

- No copy into a serving bucket. The product API's Pod Identity role gets `s3:GetObject` on `arn:aws:s3:::<bucket>/artifacts/*` (and the replicas) plus `kms:Decrypt`. It has no other permission on the bucket.
- GPU hosts still hold no AWS credentials: the existing adapter-download grant path (`product/packages/control/src/training/downloads.ts`, the GPU-control listener) presigns GETs for the hosts. Its key check gains the `artifacts/<ws>/<sha256>.grad.tar.gz` form next to today's `runs/` and `cartridges/` forms.
- The loader opens the bundle with the hardened reader rules in ARTIFACT_FORMATS (regular files only, manifest checksums, member and byte caps) and serves the format's config file, never the trainer's informational manifest fields.

### 2.4 Pin contract

Publishing a Version pins its artifact. grad never deletes a pinned artifact: not by retention, not by workspace cleanup, not by orphan sweeps.

Table `grad_artifact_pins (workspace_id, artifact_id, holder, created_at, PRIMARY KEY (workspace_id, artifact_id, holder))`. `holder` is `inference:version:<task_versions.id>`.

| Call                                                      | Caller                          | Behaviour                                                                                                                                                                                                                      |
| --------------------------------------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `PUT /v1/artifacts/{id}/pins/{holder}`                    | Product API, service JWT (§3.4) | Idempotent. `404` if the artifact is not in the token's workspace; `409 artifact_not_servable` for checkpoints and `reference` bundles. Returns the artifact (format, `sha256`, `size_bytes`, base model, revision, manifest). |
| `DELETE /v1/artifacts/{id}/pins/{holder}`                 | Product API, service JWT        | Idempotent. Called when a Version is deleted.                                                                                                                                                                                  |
| `GET /v1/artifacts/{id}` → `pins: [{holder, created_at}]` | Anyone with `artifacts:read`    | Users see why an artifact cannot be deleted.                                                                                                                                                                                   |

- `DELETE /v1/artifacts/{id}` on a pinned artifact returns `409 artifact_pinned` with the holders.
- Every grad deletion path (`deleteArtifact`, retention, workspace purge, orphan sweep) runs one SQL guard: `NOT EXISTS (SELECT 1 FROM grad_artifact_pins ...)`, in the same transaction as the delete, and deletes the S3 object only when no other artifact row has the same `(workspace_id, sha256)`.
- Pin before Version: the product API pins, then inserts the Version; a failed insert unpins. A leaked pin only retains bytes; a missing pin is impossible because the Version insert waits for the pin.
- Bucket versioning keeps a deleted object's noncurrent version for 30 days, so a bug in the guard is recoverable.

### 2.5 Publishing and naming

For deploy, the only new inference-side features are **publish from artifact** and the pin calls above. Promote, rollback and history already exist and are unchanged.

`POST /api/v1/workspaces/{ws}/tasks/{task}/versions` (product API, public, `Idempotency-Key`):

```json
{ "artifact_id": "art_…", "name": "2026-11-26-1", "eval_only": false }
```

1. Pin the artifact in grad (returns its metadata).
2. Check the format is servable (`peft_lora`, `cartridge` in M1; `encoder_safetensors`, `router_bundle`, `decision_bundle` in M2) and `base_model_revision` matches a pool's pinned revision; otherwise `422 format_not_servable` or `422 base_revision_mismatch`.
3. Insert an `unavailable` Version with `adapter.artifact_uri = s3://<bucket>/artifacts/<ws>/<sha256>.grad.tar.gz`, `sha256`, `size_bytes` and `adapter.source = {kind: "grad", artifact_id, source}`. Idempotent on `(task_id, artifact_id)`.
4. Qualify on serving capacity as today. Promote is a separate call.

Naming:

- The Model name defaults to the artifact name and the Version name to the artifact version (`fast-diff-merge` / `2026-11-26-1`), served as `<org-slug>/fast-diff-merge` and pinned as `<org-slug>/fast-diff-merge/2026-11-26-1`.
- Publishing into a differently named Model is allowed (`grad deploy fast-diff-merge@2026-11-26-1 --model support`). The Model is created on first publish. The org-wide name uniqueness of `tasks` applies: a name owned by another workspace returns `409 model_name_taken`.
- Serving raises its LoRA rank cap (`MAX_UPLOADED_ADAPTER_RANK`, `product/packages/contracts/src/training.ts`) to 32, grad's default; grad changes nothing.
- Artifact-backed Versions never fall back to the base model when no LoRA capacity is free: they fail with `capacity_exceeded` (today the gateway falls back silently).

### 2.6 `deploy()` belongs to inference

- grad-server drops deployments entirely: `/v1/deployments*`, `/v1/route`, `/v1/embeddings`, `/v1/feedback` and their 501 stubs leave `server/api/src/routes/deployments.ts` and `spec/openapi.yaml`.
- Every SDK's `deploy()` / `grad deploy` calls the product API directly (publish, wait for qualification, promote). `rollback()` and `status()` call the existing promote and history endpoints. `route`, `embeddings` and `feedback` call the gateway. These clients are a small hand-written Cloud module in each SDK, typed against the product API's OpenAPI, at parity across Python, TypeScript, Go and Rust.
- Self-hosted users get a clear `deploy_unavailable` error from the SDK itself (no Cloud base URL) with the hint to download the artifact and serve it on vLLM or SGLang.

### 2.7 Migrating the model-uploads flow

Today `POST /api/v1/workspaces/{ws}/model-uploads` plus `PUT …/model-uploads/{id}/version` uploads PEFT/cartridge files into the product bucket and creates a Version.

1. Ship `grad artifacts upload` and `import` (M1).
2. The console's upload page calls grad's upload API, then publish (M2).
3. `model-uploads` answers `410 use_grad_artifacts_upload` for new uploads; completing an upload already started keeps working for 24 h.
4. Backfill: a one-shot job imports every existing Version's files as a grad artifact (`source: import`, `provenance.legacy_version_id`), pins it, and rewrites `adapter.artifact_uri`. Versions keep their ids, names and production pointers.
5. Once no Version references the old prefixes, delete `runs/` and `cartridges/` from the product bucket, the upload routes, `model_uploads` and `upload-store.ts`.

## 3. Auth

### 3.1 Keys

- One control-plane-owned `grad_` key (`api_keys`) works for inference and training. Keys are created and revoked only in the console or the product API; grad's `/v1/keys` answers `501 keys_managed_by_cloud` in `AUTH_MODE=cloud` and is not routed on the ALB.
- v0 permissions are role-based, from the key creator's membership:

| Role     | grad scopes                                                                                                       |
| -------- | ----------------------------------------------------------------------------------------------------------------- |
| `admin`  | `admin` (every workspace scope)                                                                                   |
| `member` | `datasets:read/write`, `runs:read/write` (evals included), `artifacts:read/write`, `sources:read`, `secrets:read` |

- Product migration now: `api_keys.scopes text[] NULL`. `NULL` or empty means the role's full rights; a non-empty list is intersected with the role. Per-key permissions later are a console feature, not a migration.
- `trainer:worker` is never a customer scope; grad already drops unknown scopes.

### 3.2 `auth_principals_v1`

A view in the product database, owned by the product's migrations, `security_barrier`, readable only by role `grad_auth_reader` (`GRANT SELECT` on the view, nothing else; `CONNECTION LIMIT 10`). It returns only usable principals, so grad needs no business rules: a row exists iff the key is unrevoked, the member is active, the organization is an active customer and the workspace is not archived.

| Column              | Type          | Notes                                                    |
| ------------------- | ------------- | -------------------------------------------------------- |
| `key_digest`        | `bytea`       | SHA-256 of the secret, as `api_keys.digest`. Lookup key. |
| `api_key_id`        | `uuid`        |                                                          |
| `organization_id`   | `uuid`        |                                                          |
| `organization_slug` | `text`        | Model namespace prefix                                   |
| `workspace_id`      | `uuid`        | grad's workspace id                                      |
| `user_id`           | `uuid`        | Key creator; `actor = key:<api_key_id>`                  |
| `role`              | `text`        | `admin` \| `member`                                      |
| `scopes`            | `text[]`      | `api_keys.scopes`; NULL = role default                   |
| `expires_at`        | `timestamptz` | NULL = no expiry; grad checks `expires_at > now()`       |

- Versioning: columns are only added. A breaking change ships `auth_principals_v2` alongside, and v1 is dropped once grad no longer reads it.
- grad query: `SELECT … FROM auth_principals_v1 WHERE key_digest = $1`. Cache by token hash: positive 15 s (the gateway's `GATEWAY_RECORD_CACHE_TTL_SECONDS`), negative 5 s, 10k entries LRU. Revocation and suspension therefore lag at most 15 s on both planes.
- Failure: product DB unreachable → `503 auth_unavailable` for uncached keys; cached keys keep working until their TTL. This is the same failure an HTTP verify call would have; the view is chosen because it removes a product endpoint, not for isolation. Trainer workers authenticate with grad-local keys and never touch the view.
- The real isolation step is §3.5: once SDKs exchange keys for JWTs, grad drops the DB role.

### 3.3 Console JWTs

The console calls grad's public API with short-lived JWTs. These replace the hidden per-member API keys for training: today `createHiddenCredential` (`product/packages/control/src/workspaces/service.ts`) mints an `api_keys` row with `hidden = true`, one per member and purpose, rotated on every call, valid one hour (`PLAYGROUND_CREDENTIAL_LIFETIME_MS`).

Token endpoint (product API, session cookie, CSRF-checked):

```
POST /api/v1/workspaces/{workspace_id}/training-tokens
→ 200 {"token": "<jwt>", "expires_at": "2026-11-27T12:05:00Z"}
   403 if the member cannot read the workspace
```

| Claim / header   | Value                                          |
| ---------------- | ---------------------------------------------- |
| `alg`, `kid`     | `ES256`; the KMS key version                   |
| `iss`            | `https://api.gradiated.com`                    |
| `aud`            | `training`                                     |
| `sub`            | `user:<user_id>` (or `service:<name>`, §3.4)   |
| `org`, `ws`      | organization and workspace UUIDs               |
| `role`           | `admin` \| `member`                            |
| `scopes`         | optional; same meaning as `api_keys.scopes`    |
| `platform_admin` | staff tokens only (grad's ops UI, §7)          |
| `iat`, `exp`     | lifetime 5 min; the console refreshes at 4 min |
| `jti`            | random; for audit logs                         |

- Signing key: an asymmetric KMS key (`ECC_NIST_P256`, `kms:Sign` for the product API role only). JWKS at `GET https://api.gradiated.com/.well-known/jwks.json`, holding the current and previous key versions.
- grad verifies signature, `iss`, `aud = training`, `exp` (60 s skew) and that `ws` is a UUID; it caches JWKS for 10 min and refetches on an unknown `kid` (at most once per 30 s). No DB read on the JWT path.
- Retiring hidden keys: (1) console training pages use JWTs from day one and never mint a training hidden key; (2) the gateway accepts `aud=inference` JWTs, and the playground and the OAuth/MCP inference credential move to them; (3) delete `createHiddenCredential`, revoke the remaining hidden rows and drop `api_keys.hidden`.

### 3.4 Service JWTs

The product API calls grad (pins, artifact lookups, workspace hooks) with JWTs it signs itself: `sub = service:inference`, `aud = training`, `ws` set, `scopes = ["artifacts:pin"]` or `["workspaces:admin"]`, lifetime 5 min. No shared secret flows product → grad.

grad → product calls go to a private product API listener (`TRAINING_INTERNAL_PORT=3005`, ClusterIP only) with a static bearer `TRAINING_INTERNAL_TOKEN` (≥32 random bytes, constant-time compare, two values accepted during rotation). It is not the unauthenticated GPU-control listener and does not apply the public per-IP limiter.

### 3.5 Later: SDK key → JWT exchange

`POST /api/v1/auth/token {"grant_type": "api_key", "audience": "training"}` with `Authorization: Bearer grad_…` → the same JWT. SDKs exchange once and refresh before `exp`. When every supported SDK version does this, grad stops accepting raw `grad_` keys in Cloud, and the `grad_auth_reader` role and the view are dropped.

### 3.6 Workspace lifecycle hooks

`PUT /v1/admin/workspaces/{ws}/state` on grad (service JWT, `workspaces:admin`), idempotent:

| `state`     | Sent when                                         | grad behaviour                                                                                                                                                     |
| ----------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `suspended` | Organization suspended or workspace archived      | Refuse new jobs (`403 workspace_suspended`); heartbeats return `should_stop`, so running jobs checkpoint and stop resumable (as `stopped_balance`); sources pause. |
| `active`    | Reinstated                                        | Accept jobs; sources resume.                                                                                                                                       |
| `deleted`   | Workspace hard-deleted, after its Models are gone | Cancel jobs, release every `inference:*` pin of the workspace, purge rows and `ws/<ws>/` + `artifacts/<ws>/` after 7 days.                                         |

The auth view already stops new API calls within 15 s; the hook stops running work and owns data deletion.

## 4. Billing

### 4.1 `usage_events`

One ClickHouse table for both planes. The money ledger stays `balance_transactions`; `usage_events` is the record of what was billed, for usage views, invoices and Metabase.

```sql
CREATE TABLE usage_events (
  event_id         String,                    -- globally unique; idempotency key
  organization_id  UUID,
  workspace_id     UUID,
  product          LowCardinality(String),    -- inference | training
  sku              LowCardinality(String),    -- e.g. train:qwen/qwen3-8b, inference:<model>:prompt
  quantity         UInt64,                    -- in the SKU's unit (tokens)
  amount_nano_usd  Int64,
  price_version    LowCardinality(String),
  occurred_at      DateTime64(6, 'UTC'),
  subject_id       String,                    -- run, eval or generation id
  tags             Map(LowCardinality(String), String),  -- lane=eval, eval_id, attempt, recipe_kind, api_key_id
  ingested_at      DateTime64(6, 'UTC') DEFAULT now64(6)
) ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (organization_id, workspace_id, occurred_at, event_id);
```

Inserts use `insert_deduplication_token = event_id`; readers collapse by `event_id` (no ReplacingMergeTree, per DATA_MODEL).

### 4.2 Price list

Billing owns every price, inference and training. Training SKUs are `train:<base_model>` at a fixed price per million tokens; users never see GPU time or spot vs on-demand.

```
GET /api/internal/v1/billing/prices?product=training      (internal listener)
→ 200 {"price_version": "pv_…", "effective_at": "…",
       "skus": [{"sku": "train:qwen/qwen3-8b", "unit": "token",
                 "price_nano_usd_per_mtok": 2000000000}]}
   ETag; 304 on If-None-Match
```

- Price versions are immutable and kept forever. grad polls every 5 min, keeps the last version for up to 24 h if billing is unreachable, then refuses new runs and evals with `503 billing_unavailable`.
- A run pins the `price_version` it was planned and created with; price changes never touch running work.
- Eval inference and judge tokens are priced from the inference SKUs in the same list (for plan-time estimates only; the gateway bills them, §5).

### 4.3 Ingest

grad's `grad_usage` ledger (append-only, one row per billed increment of a run or eval attempt) is pushed, not pulled.

```
POST /api/internal/v1/billing/usage-events     (internal listener, ≤500 events)
{"events": [{"event_id": "training:run-usage:<run_id>:<attempt>:<tokens_through>",
             "workspace_id": "<uuid>", "product": "training", "sku": "train:qwen/qwen3-8b",
             "quantity": 1048576, "amount_nano_usd": 2097152000, "price_version": "pv_…",
             "occurred_at": "…", "subject_id": "run_…", "tags": {"attempt": "2", "recipe_kind": "sft"}}]}
→ 200 {"accepted": 500, "duplicates": 0}
   422 {"code": "price_mismatch" | "unknown_workspace", "event_id": "…"}   # alerts; never silently dropped
```

- Billing resolves `organization_id` from the workspace, recomputes `amount_nano_usd = round_half_up(quantity × price / 10^6)` from the stated version, posts one `balance_transactions` row per event (`type = usage`, `source_type = usage_event`, `source_id = event_id`; the unique `(source_type, source_id)` makes replays free) and inserts the `usage_events` row. The gateway replays non-settlement ledger rows into its Valkey balances, so admission sees training spend with no gateway change.
- grad changes: `grad_usage.cost_usd` becomes `amount_nano_usd BIGINT`; a `txid xid8 DEFAULT pg_current_xact_id()` column; the exporter keeps its own `(txid, seq)` cursor and reads only rows from transactions older than `pg_snapshot_xmin(pg_current_snapshot())`, so out-of-order commits are never skipped. The existing `billing/usage/cursor` call goes away.

### 4.4 Balance check and stop on balance

Both already exist in grad (`checkCanStartRun`, `canContinue`, run status `stopped_balance`); only the contract moves to integers.

```
POST /api/internal/v1/billing/check {"workspace_id": "…", "estimated_amount_nano_usd": 5000000000}
→ 200 {"allowed": true} | {"allowed": false, "reason": "insufficient_balance" | "suspended"}
```

- Start: grad passes the new job's `max_cost_usd` plus the remaining caps of the workspace's open jobs. Invoiced accounts are always allowed; prepaid needs `balance ≥ estimate`.
- Running: workers report tokens; grad writes an increment every 5 min or 10M tokens and pushes it; each heartbeat consults `canContinue` (cached 30 s per workspace). `allowed: false` → `should_stop: insufficient_balance` → checkpoint, bill the attempt, status `stopped_balance`; resume after top-up. A billing outage never stops running work. Overshoot is bounded by one increment plus `max_cost_usd`.

### 4.5 Migrating inference onto `usage_events`

The inference money path (gateway Valkey balances → settlement batches → `balance_transactions`) does not change.

1. Create `usage_events`; training writes it from day one.
2. The worker's settlement loop also inserts one `usage_events` row per settled generation and priced token type (`event_id = inference:gen:<id>:<type>`, `product = inference`, tags from the generation, including `lane=eval`).
3. Backfill from `generations` for the retention window.
4. Move the usage API, console usage pages, Metabase and invoices to `usage_events`; check totals against `balance_transactions` per day for a month.
5. `generations` stays the gateway's raw event table for analytics and settlement input; nothing bills from it directly.

## 5. Evals on Cloud

Evals are a grad job kind run by CPU eval workers (KEDA-scaled, §8). On Cloud their model calls go to the gateway.

1. **Eval-only Versions.** To evaluate an artifact that has no Model, grad publishes it with `eval_only: true` (§2.5) into a hidden per-workspace Model `grad-eval-<workspace_id>` with the artifact id as Version name. Eval-only Versions are hidden from model lists, never promotable, callable only by eval-lane credentials, unpinned and deleted 7 days after the eval finishes. Catalog bases are called by their gateway ids (lowercase aliases in the product catalog).
2. **Credentials.** grad requests a per-eval key for the worker:

   ```
   POST /api/internal/v1/training/eval-credentials {"workspace_id": "…", "eval_id": "ev_…", "ttl_seconds": 21600}
   → 200 {"api_key": "grad_…", "expires_at": "…"}
   ```

   It is an `api_keys` row of the workspace with `lane = eval` and `scopes = ["inference"]`, revoked when the eval finishes. It travels only in the eval job's claim payload to eval-kind workers.

3. **Eval lane.** The gateway treats `lane = eval` keys as lowest priority: a separate per-workspace rate limit (default 20 concurrent, 600 rpm), never counted as demand by pool autoscaling, and shed first with `429` under capacity pressure. Eval workers back off on 429.
4. **Billing once.** The gateway bills model and judge tokens as normal generations, tagged `lane=eval, eval_id`. grad records its eval `grad_usage` rows with `billed_by = gateway`, shows them in `/v1/usage`, and never pushes them. Plan-time estimates use the inference prices from §4.2.

## 6. GPU sharing

Training is a preemptible tenant of the existing gpu-fleet. There is no training pool, no pool controller and no isolated training account.

### 6.1 Behaviour

- **Lease on demand.** The operator reads `max(grad_jobs_open{kind="train"})` from Prometheus (claimable plus leased train jobs; each v0 job needs one GPU). When it exceeds the GPUs on grad-held hosts for 2 min, the operator leases one spare host to holder `grad`, up to `GRAD_MAX_GPUS`. A spare host is Ready, unreserved, uncordoned, runs no serving pod, and has GPUs with ≥ 80 GB (every catalog base trains on one 80 GB GPU).
- **Wipe on every switch.** Lease start re-images the host onto the pinned image before the trainer starts; return re-images it again (today's return rollout). A host is never serving and training at once.
- **Run the pinned bundle.** The operator mints a per-lease train-only key, registers its hash with grad, and asks the host agent to start one `grad-trainer` worker per GPU from the bundle pinned in `runtimes.json`.
- **Inference has priority.** As soon as a model pod is unschedulable for 30 s and would fit on a grad host, the operator reclaims that host: no ten-minute wait as for person leases. Graceful drain: host agent SIGTERMs the workers; each saves an emergency checkpoint if one fits in `GRAD_RECLAIM_GRACE_SECONDS` (60 on the fleet), completes its attempt as `compute_reclaimed` (billed, requeued at once, not counted toward `max_attempts`); SIGKILL at 90 s; then the return re-image and uncordon.
- **Scale down.** A grad host whose workers have all been idle for 15 min while demand is below the leased GPUs is returned the same way.
- **Optional training-only floor (later).** Hosts carrying `gradiated.com/reserved=training` in `hosts.yaml` are leased to `grad` permanently and never reclaimed. Default: none.

### 6.2 Operator changes (`product/services/gpu-fleet`)

1. `grad` lease planner: reads the Prometheus metric, picks spare hosts, writes the `fleet.gradiated.com/lease` request with `holder: "grad"`, `preemptible: true`, `until` = now + 24 h (renewed while busy). Config: `GRAD_MAX_GPUS`, `GRAD_LEASE_HOLD_MINUTES`, `GRAD_SERVER_URL`, `GRAD_FLEET_KEY` (secret).
2. Lease start for holder `grad` re-images before handing the host over (person leases keep today's behaviour).
3. Reclaim for holder `grad`: 30 s instead of 10 min, choosing the grad host with the most idle GPUs, then the newest lease.
4. Drain step before return: `train_stop`, wait for exit or 90 s, then the existing return rollout.
5. Keys: generate 32 random bytes per lease; `PUT {GRAD_SERVER_URL}/internal/v1/trainer-keys/{lease_id}` `{sha256, kinds: ["train"], expires_at}` before `train_start`; `DELETE` on return. Recorded on `status.lease` like the Tailscale keys it already mints and revokes.
6. Metrics and alerts: `gradiated_gpu_fleet_grad_gpus{state="leased|busy|draining"}`, lease events with outcome `reclaimed`, alert `GpuFleetGradDrainSlow` (drain > 5 min) and `GpuFleetGradDemandUnmet` (demand unmet 2 h, warning only).
7. Remove the `gpu-training` PriorityClass and training-Job handling once §10 is done.

### 6.3 Host agent changes

1. New operations, guarded by the management key: `train_start {bundle_digest, server_url, worker_key, gpus}`, `train_stop {grace_seconds}`, `train_status` → per GPU `idle | running | draining` (read from a status file each worker writes).
2. `train_start` refuses while any serving pod, GPU compute process or staged pod exists; pod creation is refused while trainers run. This enforces "never both" on the host as well as in the operator.
3. Workers run as an unprivileged `trainer` user in a cgroup with CPU, memory and process limits, `CUDA_VISIBLE_DEVICES` set to one GPU each, scratch under a trainer-only directory, and env `GRAD_SERVER_URL`, `TRAINER_API_KEY` (from a 0400 file), `GRAD_WORKER_ID=<host>/<gpu>`, `GRAD_WORKER_KINDS=train`, `GRAD_RECLAIM_GRACE_SECONDS=60`. They cannot read the management key.
4. `grad-trainer` bundle entry in `product/inference/gpu/runtimes.json` (CUDA image from GHCR, mirrored to ECR, pinned by digest), staged like other bundles.

### 6.4 grad changes

- `grad_trainer_keys (label, sha256, kinds, expires_at, revoked_at)` plus the internal `PUT/DELETE /internal/v1/trainer-keys/{label}` (worker listener, authenticated by the operator's `trainer:keys` fleet key). Static `TRAINER_KEYS_JSON` keys keep working for in-cluster CPU workers.
- Nothing else: pull workers, leases, heartbeats, `compute_reclaimed` requeue, checkpoint-on-SIGTERM and fit-aware claiming already exist.

## 7. Console

- Training pages live in the product console and call grad's public API (`https://api.gradiated.com/v1/...`) with the §3.3 JWT, through the TypeScript SDK. Live run progress uses grad's SSE stream. grad allows the console origin by CORS for `Authorization`-bearing requests (no cookies).
- grad's web UI (`/ui`) is the ops and backend UI only. In Cloud it is off on the public listener and served on the worker listener over Tailscale to staff, authenticated with a staff JWT (`platform_admin: true`).
- The console never reads grad's database:
  - **Business logic** (planning, validation, state machines, cost estimates) lives in grad's services; reading tables would reimplement it.
  - **Tenant scoping** and scopes are enforced per request by grad; a DB reader bypasses both.
  - **Schema churn:** grad's schema is internal to an OSS project on 0.x and migrated by grad's releases.
  - **Writes** must go through grad's idempotent APIs and queue semantics.
  - **SSE:** live events come from grad's per-replica event hub; a DB poll per page is exactly what grad removed.
- Cross-plane reporting (spend, usage by workspace, training next to inference) reads ClickHouse `usage_events`, not grad.

## 8. Deployment

| Item           | Value                                                                                                                                                                                                                                                                                                            |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Namespace      | `training` in the prod EKS cluster; Argo CD Application from grad's Helm chart (OCI) plus a values file in infra                                                                                                                                                                                                 |
| grad-server    | 2 replicas, `AUTH_MODE=cloud`, `BILLING_MODE=cloud`; listeners: public `:8787` (customer API) and worker `:8788` (`/v1/trainer-jobs/*`, `/internal/v1/*`, `/ui`, `/metrics`)                                                                                                                                     |
| Workers in EKS | CPU Deployments `import` (file imports, artifact upload/import validation, source syncs; the only kind that sees workspace secrets) and `eval`; KEDA `prometheus` trigger on `grad_jobs_open{kind=…}`, min 0 (`import` min 1)                                                                                    |
| GPU workers    | Leased fleet hosts only (§6); none in EKS                                                                                                                                                                                                                                                                        |
| Database       | Logical database `grad` on the existing `gradiated-prod` RDS (Postgres 17), owner role `grad_server` (`REVOKE CONNECT ON DATABASE gradiated FROM grad_server`); role `grad_auth_reader` in `gradiated` with `SELECT` on `auth_principals_v1` only; `sslmode=verify-full`                                         |
| S3             | Bucket and prefixes of §2.2; lifecycle rules: tag `grad-state=staging` expires after 2 days; noncurrent versions 30 days; replication of `artifacts/` per serving region                                                                                                                                         |
| AWS identity   | Pod Identity (no IRSA). `gradiated-prod-grad-server`: read/write on the bucket, its KMS key. Product API role: `s3:GetObject` on `artifacts/*` and replicas, `kms:Decrypt`, `kms:Sign` on the JWT key. Workers: no AWS role (presigned URLs only)                                                                |
| Secrets        | `gradiated/prod/training/grad-server`: `databaseUrl`, `authDatabaseUrl`, `trainingInternalToken`, `secretsKey`, `trainerKeysJson`, `fleetKeySha256`. Product api: `TRAINING_INTERNAL_TOKEN`. gpu-fleet: `GRAD_FLEET_KEY`. ESO `SecretStore` per namespace                                                        |
| ALB routes     | `api.gradiated.com` `/v1/{datasets,runs,checkpoints,artifacts,evals,imports,uploads,sources,secrets,base-models,usage}` → grad-server `:8787` (HTTPRoute in `gradiated`, `ReferenceGrant` in `training`). Never `/v1/keys`, `/v1/trainer-jobs`, `/internal`, `/ui`; grad 404s them on the public listener anyway |

Network policies (VPC CNI network policy enabled; default-deny in `training`):

| From                                                           | To                                                                             | Why                                              |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------ |
| ALB                                                            | grad-server `:8787`                                                            | Customer API, console                            |
| Product API (`gradiated`)                                      | grad-server `:8787`                                                            | Pins, artifact lookup, workspace hooks           |
| gpu-fleet operator                                             | grad-server `:8788`                                                            | Trainer key registry                             |
| Leased GPU hosts (Tailscale `tag:gpu` → `tag:grad-worker-api`) | grad-server `:8788`                                                            | Worker protocol                                  |
| `import`, `eval` workers                                       | grad-server `:8788`                                                            | Worker protocol                                  |
| `eval` workers                                                 | gateway (in-cluster Service)                                                   | Eval inference                                   |
| `import` workers                                               | `0.0.0.0/0:443` except RFC 1918, `100.64.0.0/10`, `169.254.0.0/16`, `fd00::/8` | Source providers, HF Hub (SSRF guard)            |
| grad-server                                                    | RDS `:5432`, product API `:3005`, product API JWKS, S3, DNS                    | DB, auth view, billing, prices, eval credentials |
| Prometheus                                                     | grad-server `:8788/metrics`                                                    | KEDA and the operator's demand metric            |

Nothing in `gradiated` or `gpu-inference` calls grad on a request path, and the gateway has no route to grad at all.

## 9. Failure matrix

| Down                   | Still works                                                                                      | Stops or degrades                                                                                                                                           |
| ---------------------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| grad-server or grad DB | All inference: serving, promote, rollback, history, gateway feedback, already-published Versions | Training API and console training pages; new publishes from artifacts (pin call); workers retry heartbeats, then leases expire and jobs requeue on recovery |
| Product DB (auth view) | Running training jobs; console JWT calls (JWKS cached); keys cached < 15 s                       | New key-authenticated grad calls → `503 auth_unavailable`; billing checks → new jobs `503`; inference itself is down                                        |
| Product API            | Running jobs (fail-open `canContinue`); grad API for cached keys; prices for 24 h                | JWT minting (console), new jobs (balance check), usage push (backlog in `grad_usage`, drained later), eval credentials, publish                             |
| Gateway                | Training, imports, downloads                                                                     | Evals (retry with backoff); all inference                                                                                                                   |
| ClickHouse             | Training, inference, balances (ingest commits the ledger first)                                  | Usage ingest returns 503 → grad retries; usage views stale                                                                                                  |
| S3                     | Inference with adapters already loaded                                                           | Everything that moves bytes on both planes                                                                                                                  |
| gpu-fleet operator     | Running training on leased hosts; serving                                                        | No new grad leases, no reclaim: inference cannot take hosts back until it recovers (alerted)                                                                |
| Prometheus             | Reclaim (driven by pending pods from the Kubernetes API); running jobs                           | No new grad leases (holds current); KEDA keeps current replicas                                                                                             |
| Tailscale              | Serving traffic already routed                                                                   | GPU workers lose grad; leases expire, jobs requeue (`worker_lost`)                                                                                          |
| A leased GPU host      | Everything else                                                                                  | Its jobs requeue after lease expiry, not counted toward `max_attempts`                                                                                      |

## 10. Retiring the old training stack

The old stack: Temporal workflows in `product/services/temporal-worker/src/training` (the only Temporal user) with `packages/temporal`; training Kubernetes Jobs on virtual-kubelet nodes (`gpu-training` PriorityClass, `kubernetes-host.ts`, training runtimes in `runtimes.json`); `training_runs`, `training_run_events` and `tasks.training_schedule`; the model-uploads path and the product bucket's `runs/` and `cartridges/` prefixes.

1. grad on Cloud reaches M1; console training pages switch to grad.
2. Feature-flag off new product training runs and schedules; let in-flight Temporal runs finish or cancel them.
3. Backfill existing Versions into grad artifacts (§2.7 step 4). Export `training_runs`/`training_run_events` to S3 for audit.
4. Remove the Temporal training workflows and worker, the `temporal-worker` Deployment and its secrets, then the Temporal Cloud namespace.
5. Remove training Jobs from virtual-kubelet and the host agent, the `gpu-training` PriorityClass and training runtimes.
6. Switch model-uploads to `410`, then remove its routes and tables (§2.7 step 5).
7. Drop `training_runs`, `training_run_events`, `model_uploads` and the unused `tasks` training columns, keeping `tasks` and `task_versions`.

## 11. Work breakdown

**M1: import, train, eval and download for Cloud users.** **M2: deploy from artifacts, gateway feedback and the `gradiated` source.** Order within each list is the dependency order.

### grad repo

| #   | M   | Task                                                                                                                                                                                              |
| --- | --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| G1  | 1   | Drop `/v1/deployments*`, `/v1/route`, `/v1/embeddings`, `/v1/feedback` and their stubs; regenerate OpenAPI and SDK transports; `/v1/keys` 501 in cloud mode                                       |
| G2  | 1   | Cloud auth: `auth_principals_v1` reader (pg pool, 15 s/5 s cache), JWT verifier (JWKS, `aud=training`), role → scopes; remove the HTTP verify adapter                                             |
| G3  | 1   | Two listeners (public `:8787`, worker `:8788`); public listener 404s worker, internal and UI routes                                                                                               |
| G4  | 1   | Billing: price-list client (ETag, 24 h stale limit, run-pinned `price_version`), integer `amount_nano_usd`, xid8 exporter to `usage-events`, integer balance check; eval rows `billed_by=gateway` |
| G5  | 1   | Artifact layout: `artifacts/<ws>/<sha256>` for releases, promote = copy, manifest `source` + `provenance`; `grad_artifact_pins`, pin API, deletion guard                                          |
| G6  | 1   | `grad artifacts upload` and `import hf://` (staging upload, CPU import validation and bundling) in the CLI and all four SDKs                                                                      |
| G7  | 1   | Trainer key registry + `/internal/v1/trainer-keys`; fleet key scope `trainer:keys`                                                                                                                |
| G8  | 1   | Cloud evals: request eval credentials, publish eval-only Versions via the product API, map refs to gateway names, back off on 429                                                                 |
| G9  | 1   | Workspace state hook; CORS for the console origin; `/ui` behind staff JWT on the worker listener                                                                                                  |
| G10 | 2   | Cloud SDK module in Python, TS, Go and Rust: `deploy()`, `rollback()`, `status()`, `route`, `embeddings`, `feedback` against the product API and gateway; CLI `grad deploy`                       |
| G11 | 2   | `gradiated` source provider (Cloud adapter over `training/traces:pull`)                                                                                                                           |

### product repo

| #   | M   | Task                                                                                                                                                                                                                                |
| --- | --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1  | 1   | Migration: `api_keys.scopes`, `auth_principals_v1` view, `grad_auth_reader` grants                                                                                                                                                  |
| P2  | 1   | JWT: KMS signing, JWKS endpoint, `POST …/training-tokens`, service JWT helper                                                                                                                                                       |
| P3  | 1   | Internal listener `:3005`: `billing/prices`, `billing/check` (nano-USD), `billing/usage-events` ingest → `balance_transactions` (`source_type = usage_event`) + ClickHouse `usage_events`; training SKUs in the price list          |
| P4  | 1   | Publish from artifact (`POST …/tasks/{task}/versions {artifact_id}`) for `peft_lora` and `cartridge`, `eval_only` Versions, pin/unpin calls, grant issuer accepts `artifacts/`, rank cap 32, no base fallback for artifact Versions |
| P5  | 1   | `training/eval-credentials`; gateway eval lane (key `lane`, rate limit, autoscaling exclusion, `lane=eval` tags)                                                                                                                    |
| P6  | 1   | Console training pages on the TS SDK with JWTs: datasets and imports, runs with live progress, evals, artifacts and downloads, usage                                                                                                |
| P7  | 1   | Workspace suspend/reinstate/delete hooks to grad                                                                                                                                                                                    |
| P8  | 2   | Console deploy flow (publish + promote), artifact upload page on grad, model-uploads `410` and backfill (§2.7)                                                                                                                      |
| P9  | 2   | Serving for `encoder_safetensors` (`/v1/embeddings`), `router_bundle` (`/v1/route`) and `decision_bundle`                                                                                                                           |
| P10 | 2   | Gateway feedback endpoint → ClickHouse with traces; `training/traces:pull` with the late-score watermark                                                                                                                            |
| P11 | 2   | `usage_events` for inference (§4.5); hidden-key retirement steps 2–3 (§3.3)                                                                                                                                                         |
| P12 | 2   | Retire the old training stack (§10)                                                                                                                                                                                                 |

### infra (infra repo and the fleet)

| #   | M   | Task                                                                                                                                         |
| --- | --- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| I1  | 1   | Terraform: bucket, KMS, lifecycle rules, Pod Identity roles, JWT KMS key, ECR repos (`grad-server`, `grad-trainer`), Secrets Manager entries |
| I2  | 1   | RDS bootstrap job: database `grad`, roles `grad_server` and `grad_auth_reader`                                                               |
| I3  | 1   | `training` namespace, SecretStore, ExternalSecrets, Argo Application and values, HTTPRoutes + ReferenceGrant, KEDA ScaledObjects             |
| I4  | 1   | Tailscale `tag:grad-worker-api` Service and ACL grant from `tag:gpu`, with policy tests                                                      |
| I5  | 1   | VPC CNI network policy on (cluster-wide, scheduled) and the `training` policies of §8                                                        |
| I6  | 1   | gpu-fleet operator and host agent changes (§6.2, §6.3), `grad-trainer` bundle pin; first in `MODE=observe`, then act                         |
| I7  | 1   | LoRA-enabled pools for every catalog base at grad's pinned revisions (scale to zero allowed) so evals and deploys have capacity              |
| I8  | 2   | S3 replication of `artifacts/` to each serving region                                                                                        |

## Open questions

1. **Eval capacity.** Evals need a LoRA-enabled pool per catalog base. Scale-to-zero pools make the first eval wait minutes; standing pools cost GPU hours. Which bases get a floor?
2. **Scheduled retraining.** `tasks.training_schedule` (retrain from traces on a cron) has no grad equivalent. Drop it, or add scheduled runs on top of the `gradiated` source?
3. **Operator as a single point for reclaim.** If the operator is down, grad hosts are not returned. Should the host agent enforce `until` on its own (stop trainers at lease expiry without the operator)?
4. **Usage backlog.** If ingest is down for long, grad keeps starting runs against a balance that lags. Refuse new runs when unpushed usage exceeds a threshold?
5. **Member rights.** The product requires `admin` for training writes today (`requireWorkspaceEditor`); §3.1 lets members train. Confirm.
6. **Regions.** Which serving regions get an `artifacts/` replica (EU hosts exist today)?
