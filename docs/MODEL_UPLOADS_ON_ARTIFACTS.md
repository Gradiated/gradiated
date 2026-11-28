# Model uploads on grad artifacts

- status: plan; the first step (closing new uploads behind a flag) is implemented
- related: [TRAINING_CLOUD_INTEGRATION.md](TRAINING_CLOUD_INTEGRATION.md) §2.7, [TASK_FINE_TUNING_SERVING_CONTRACT.md](TASK_FINE_TUNING_SERVING_CONTRACT.md), grad's `docs/ARTIFACT_FORMATS.md`

Today `POST /api/v1/workspaces/{ws}/model-uploads` plus `PUT …/model-uploads/{id}/version` stages PEFT LoRA or cartridge files in the product bucket, validates them in the API process and writes a Version whose `adapter.artifact_uri` points at `runs/<id>/output/<sha>/adapter.tar.gz` or `cartridges/<id>/<sha>/cartridge.safetensors`. After this plan, every servable file is a grad artifact: uploads go through `grad artifacts upload`, and a Version only ever points at `artifacts/<ws>/<sha256>.grad.tar.gz` in the training bucket, pinned for as long as the Version exists.

## What changes for users

| Before                                                   | After                                                                                                                                 |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Console upload page, `model-uploads` API                 | `grad artifacts upload ./adapter --base qwen/qwen3-8b --name support` (CLI or any SDK), or the console page on grad's upload API (P8) |
| The upload creates a Version directly                    | The upload creates an artifact; `POST …/tasks/{task}/versions {artifact}` publishes it (or `grad deploy`)                             |
| Validation in the product API, one at a time per process | Validation in grad's CPU import worker, against `ARTIFACT_FORMATS.md`, and again by the publish path's hardened reader                |

## Steps

1. **Publish from artifacts (this stack, PR 1).** `POST …/tasks/{task}/versions {artifact}` exists, pins, and reads bundles in place.
2. **Close new uploads (this PR).** With `MODEL_UPLOADS_CLOSED=true` the API answers `POST …/model-uploads` with `410 use_grad_artifacts_upload`, naming `grad artifacts upload`. `PUT …/model-uploads/{id}/version` keeps working for uploads already started: they expire one hour after their grant, so no window longer than that is needed. Default off; turn it on once the console upload page uses grad (P8).
3. **Backfill existing uploaded Versions** (one-shot job, below). Versions keep their IDs, names, production pointers and history rows.
4. **Retire the old path** (in the retirement PR, after 3 has run in production and `SELECT count(*) FROM task_versions WHERE NOT adapter ? 'source'` is 0): delete the `model-uploads` routes, `uploads.ts`, `upload-store.ts`, `adapter-upload.ts`'s archive writer, the `model_uploads` table, and the product bucket's `runs/` and `cartridges/` prefixes (30-day noncurrent versions stay as the undo).

## Backfill job

For each Version whose `adapter` has no `source` (trained by the old stack or uploaded), in `created_at` order, idempotently:

1. Read the Version's archive from the product bucket and check its `sha256` and `size_bytes` (as the hosting grant does).
2. Build the upload file: LoRA archives are already `adapter_config.json` + `adapter_model.safetensors`; a cartridge is tarred as `cartridge.safetensors`.
3. `POST /v1/uploads {purpose: "artifact_import", filename, size_bytes, sha256}` on grad (service JWT for the Version's workspace, scope `artifacts:write`), then PUT the bytes with the ticket's headers. Uploads are content-addressed, so a retry re-uses the same `upload_id`.
4. `POST /v1/artifact-imports {source: {upload_id}, base_model, format, name}` with `Idempotency-Key = backfill:<version_id>`; wait for the job. The artifact's provenance is `source: upload`; the job's manifest records `legacy_version_id` (grad addition, below).
5. Pin it: `PUT /internal/v1/workspaces/{ws}/artifacts/{id}/pins/inference:version:<version_id>`.
6. In one transaction, if the Version still has no `source`: set `adapter.artifact_uri`, `sha256`, `size_bytes` to the bundle's and `adapter.source = {kind: "grad", artifact_id, artifact_source: "upload", bundle: "grad.artifact/1"}`. Keep `rank`, the cartridge fields and `validated_base_model_revision`. If the update finds a `source` already, unpin.
7. Hosts pick the new archive up on their next cold load: the cache key is `<version_id>-<sha256>`, so a changed sha forces a fresh, verified download; loaded adapters keep serving.

Run it in `MODE=dry-run` first (steps 1–2 and a report of every Version, its base and whether grad accepts that base), then for one workspace, then all.

## Open problems

- **Bases.** The only LoRA pools serve `z-ai/glm-5.3-flash` and `deepseek/deepseek-v4.1-flash-1017`, so every servable uploaded Version adapts one of them. grad's catalog lists the Qwen3 bases, Linden and bge-small, so `artifact-imports` refuses these bases. The backfill needs grad to accept serving-only bases for imports (validation by shape against the pinned config, no training support), or these Versions stay on the old prefixes and block step 4.
- **Names.** grad artifact names are `^[a-z0-9][a-z0-9._-]{0,63}$`; task names may be up to 128 characters, mixed case. The job uses a lowercased, truncated task name plus the Version ID's last 8 hex characters.
- **`legacy_version_id`.** Not in grad's import API yet. Without it the link is only in the product row (`adapter.source.artifact_id`), which is enough to serve; it only affects audit.
- **Weights explorer and downloads.** Both read the archive by `artifact_uri`; they already accept the grad bundle key (PR 1), and the explorer's tar reader skips `manifest.json`.
