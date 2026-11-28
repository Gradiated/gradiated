/* What each problem `code` grad-server answers with means, and what to do.
   The codes and statuses come from the server (generated/error-codes.json);
   a test fails when the server gains a code this file doesn't explain. */

export type ErrorArea =
  | "Requests and auth"
  | "Datasets and imports"
  | "Runs and recipes"
  | "Checkpoints and artifacts"
  | "Evals and scoring"
  | "Sources and secrets"
  | "Server and capacity"
  | "Gradiated Cloud";

export type ErrorDoc = { area: ErrorArea; means: string; fix?: string };

const req = "Requests and auth" as const;
const data = "Datasets and imports" as const;
const runs = "Runs and recipes" as const;
const art = "Checkpoints and artifacts" as const;
const evals = "Evals and scoring" as const;
const src = "Sources and secrets" as const;
const server = "Server and capacity" as const;
const cloud = "Gradiated Cloud" as const;

export const ERROR_DOCS: Record<string, ErrorDoc> = {
  /* -- requests and auth -- */
  malformed_request: {
    area: req,
    means: "The body isn't valid JSON.",
    fix: "Send `Content-Type: application/json` with a JSON body. The SDKs never send this.",
  },
  validation_error: {
    area: req,
    means:
      "A field is missing, has the wrong type or is out of range. `errors[]` names each field with its path.",
    fix: "Read `errors[]` (the SDKs raise `ValidationError` with `.errors`) and compare with the endpoint in the [API reference](/docs/reference/training-api/).",
  },
  unauthorized: {
    area: req,
    means: "No API key, or the key is unknown, revoked or expired.",
    fix: "Send `Authorization: Bearer <key>`. The SDKs and CLI read `GRADIATED_API_KEY` or the profile `GRADIATED_PROFILE` names; `grad config` shows which one they use.",
  },
  forbidden: {
    area: req,
    means:
      "The key lacks the scope this endpoint needs; the message names it. Naming a workspace secret also needs `secrets:read`.",
    fix: "Create a key with that scope (`grad keys create --scopes ...`) or use an `admin` key. See [API key scopes](/docs/api-reference/#api-key-scopes).",
  },
  host_not_allowed: {
    area: req,
    means:
      "`AUTH_MODE=none` only: the request's `Host` is a public DNS name, which could be a DNS-rebinding page.",
    fix: "Reach the server by `localhost`, an IP or a compose service name, or serve the domain with `AUTH_MODE=api_key`.",
  },
  cross_site_request: {
    area: req,
    means:
      "`AUTH_MODE=none` only: a browser request from another site, which would act as the platform admin.",
    fix: "Add the page's origin to `GRAD_CORS_ORIGINS`, or run with `AUTH_MODE=api_key`.",
  },
  route_not_found: {
    area: req,
    means: "No route matches the method and path.",
    fix: "Check the base URL: grad-server serves `/v1/...` on port 8787 (`grad local up` publishes 18787).",
  },
  invalid_cursor: {
    area: req,
    means: "The `cursor` isn't one this list returned.",
    fix: "Pass `next_cursor` (or `tail_cursor` for metrics) back unchanged; start over without a cursor.",
  },
  idempotency_key_invalid: {
    area: req,
    means: "`Idempotency-Key` isn't 1 to 255 visible ASCII characters.",
    fix: "Send a UUID. The SDKs send one on every POST.",
  },
  idempotency_key_reused: {
    area: req,
    means: "This `Idempotency-Key` was used before with a different body.",
    fix: "Use a new key for a new request; reuse a key only to retry the same request.",
  },
  idempotency_replay_unavailable: {
    area: req,
    means:
      "A retried `POST /v1/keys` with the same key: the first request created the key, and its secret is shown only once.",
    fix: "List the keys to find it, or revoke it and create a new one.",
  },
  payload_too_large: {
    area: req,
    means: "The JSON body is over 32 MiB.",
    fix: "Push records in smaller batches (the SDKs send 8-16 MiB), or upload a file with `POST /v1/uploads` and import it.",
  },
  too_many_streams: {
    area: req,
    means: "This key already holds the most open event streams (SSE) it may.",
    fix: "Close a stream, or poll the JSON page with `tail_cursor` instead.",
  },
  key_not_found: {
    area: req,
    means: "No API key with this id in the workspace.",
  },
  invalid_period: {
    area: req,
    means: "A usage period is empty: `from` must be before `to`.",
  },
  workspace_suspended: {
    area: req,
    means:
      "The workspace is suspended: it can't start new jobs, and running jobs stop at their next checkpoint.",
    fix: "Contact the workspace's admin, or Gradiated support on Gradiated Cloud.",
  },
  workspace_deleted: {
    area: req,
    means: "The workspace was deleted and its data is being removed.",
  },

  /* -- datasets and imports -- */
  dataset_not_found: {
    area: data,
    means: "No dataset with this name in the workspace.",
    fix: "`grad datasets list` shows the names; `datasets.push()` creates a dataset as it pushes.",
  },
  dataset_exists: {
    area: data,
    means:
      "A dataset with this name already exists (or, for a filter, the name belongs to another dataset).",
    fix: "Push to it instead of creating it, or pick another name.",
  },
  dataset_version_not_found: {
    area: data,
    means:
      "The dataset has no such version; the message names its current version.",
  },
  empty_dataset: {
    area: data,
    means: "The dataset version has zero records.",
    fix: "Push records or wait for the import to finish, then plan again.",
  },
  no_usable_records: {
    area: data,
    means:
      "None of the records has the shape this recipe trains on; the message lists why for each kind of record.",
    fix: "Check the record shapes in [Trajectories](/docs/training/trajectories/), and preview with `grad render`.",
  },
  records_batch_conflict: {
    area: data,
    means: "A record push reused a batch number for different records.",
    fix: "Let the SDK number the batches, or give each push its own `Idempotency-Key`.",
  },
  invalid_filter: {
    area: data,
    means:
      "A score condition isn't `<op><number>` (`>=0.8`, `==1`; ops `>= <= > < == !=`).",
  },
  render_conflict: {
    area: data,
    means:
      'A record\'s `<think>` blocks contradict `thinking`: one is present with `thinking="off"`, or missing with `thinking="on"`.',
    fix: 'Use `thinking="auto"`, or fix the records.',
  },
  render_unsupported_model: {
    area: data,
    means:
      "The model isn't a chat model in the catalog, so there is no chat template to render.",
    fix: "`grad models list` shows the catalog.",
  },
  import_not_found: { area: data, means: "No import job with this id." },
  unknown_upload: {
    area: data,
    means:
      "`upload_id` isn't an upload id: it is the file's sha256 (64 hex characters).",
  },
  upload_incomplete: {
    area: data,
    means: "The upload hasn't arrived in storage yet.",
    fix: "`PUT` the file to the upload URL from `POST /v1/uploads` first, then create the import. The SDKs do both.",
  },
  upload_integrity_error: {
    area: data,
    means:
      "The uploaded bytes don't match the sha256 the upload was created with.",
    fix: "Upload the file again; check nothing rewrote it on the way (proxies, line-ending conversion).",
  },

  /* -- runs and recipes -- */
  run_not_found: { area: runs, means: "No run with this id in the workspace." },
  unknown_model: {
    area: runs,
    means:
      "The model is neither a trainable base model nor an artifact in this workspace; the message suggests a close match.",
    fix: "`grad models list` (`GET /v1/base-models`) shows the trainable models; artifacts are `name@version` or `name@latest`.",
  },
  recipe_not_supported_for_model: {
    area: runs,
    means:
      "The base model can't train this recipe; the message lists the models that can.",
    fix: "See [Supported models](/docs/training/models/).",
  },
  recipe_deferred: {
    area: runs,
    means: "The recipe isn't in v0 yet (RL and environments are coming soon).",
  },
  recipe_param_unsupported: {
    area: runs,
    means:
      "A recipe field doesn't apply to this recipe; the message names the recipes it belongs to.",
  },
  recipe_param_conflict: {
    area: runs,
    means: "A recipe field and the same setting inside `recipe.loss` disagree.",
    fix: "Set one of them.",
  },
  loss_unsupported: {
    area: runs,
    means: "This recipe doesn't train with that loss (or chooses its own).",
  },
  adapter_not_supported: {
    area: runs,
    means:
      "The base model doesn't support this adapter kind; the message lists the ones it does.",
  },
  adapter_conflict: {
    area: runs,
    means:
      "Continued training keeps the starting artifact's LoRA rank and alpha, and the recipe asked for different ones.",
    fix: "Omit `recipe.adapter`, or match the artifact's.",
  },
  continued_training_unsupported: {
    area: runs,
    means:
      "The starting artifact can't be trained further: it has no recorded LoRA adapter, or it is a merged model.",
    fix: "Continue from an artifact trained with `merge_on_export=false`.",
  },
  model_exceeds_gpu_memory: {
    area: runs,
    means:
      "The model (with its teacher, for distillation) needs more GPU memory than one training GPU has.",
    fix: "Pick a smaller model or teacher; see the GPU memory column in [Supported models](/docs/training/models/).",
  },
  cartridge_context_required: {
    area: runs,
    means: "A cartridge recipe needs the document to compress.",
    fix: "Pass `recipe.context_text` (`Context.from_file(...)` reads a local file).",
  },
  router_candidates_required: {
    area: runs,
    means: "A router needs scores for at least two candidate models.",
    fix: "Pass `recipe.models`, or train on records scored for two or more models.",
  },
  router_fallback_not_candidate: {
    area: runs,
    means: "`recipe.fallback` isn't one of the candidate models.",
  },
  router_pricing_not_candidate: {
    area: runs,
    means: "`recipe.pricing` names a model that isn't a candidate.",
  },
  router_score_out_of_range: {
    area: runs,
    means: "Router scores must be in [0, 1]; the message names the record.",
  },
  reward_rubric_unsupported: {
    area: runs,
    means:
      "`RewardModelRecipe(rubric=...)` takes the name of a score already on your records, not judge or validator items.",
  },
  reward_score_out_of_range: {
    area: runs,
    means: "Reward scores must be in [0, 1]; the message names the record.",
  },
  distill_teacher_required: {
    area: runs,
    means: "Distillation needs `teacher=`.",
    fix: "Pass a larger catalog model (such as `qwen/qwen3-14b`), or with `rollout=OffPolicy()` an artifact or any model your inference endpoint serves.",
  },
  distill_teacher_is_student: {
    area: runs,
    means: "The teacher is the student model.",
    fix: "Pass a larger teacher, or a `context=` the teacher reads and the student doesn't.",
  },
  distill_teacher_unsupported: {
    area: runs,
    means:
      "On-policy distillation loads the teacher in the trainer, which takes catalog models only.",
    fix: "To learn from an artifact, pass `rollout=OffPolicy()`.",
  },
  distill_tokenizer_mismatch: {
    area: runs,
    means:
      "On-policy distillation needs teacher and student to share a tokenizer.",
    fix: "Pick a teacher from the student's family, or pass `rollout=OffPolicy()`.",
  },
  distill_context_needs_on_policy: {
    area: runs,
    means:
      "`recipe.context` is read by the teacher during on-policy distillation, so it can't be combined with `rollout=OffPolicy()`.",
  },
  scorer_sandbox_unavailable: {
    area: runs,
    means:
      "A training recipe's rubric has code scorers, which need a managed sandbox (coming soon).",
    fix: 'Score your records first and pass the score name (`rubric="..."`), or use judges, regexes and validators.',
  },
  checkpoint_eval_code_scorer: {
    area: runs,
    means:
      "`recipe.evals` has code scorers; evals during training take judges, regexes and validators only.",
    fix: "Run code scorers in an eval of `run.artifact` after training.",
  },
  duplicate_checkpoint_eval: {
    area: runs,
    means: "Two `recipe.evals` have the same name.",
    fix: "Pass `name=` to tell evals on the same dataset apart.",
  },
  run_not_cancellable: { area: runs, means: "The run already finished." },
  run_not_resumable: {
    area: runs,
    means:
      "Only a stopped, failed or cancelled run resumes. A run cancelled a moment ago may still be stopping its worker.",
    fix: "Wait a few seconds and resume again.",
  },
  run_state_changed: {
    area: runs,
    means: "The run changed while this request was handled.",
    fix: "Retry the request.",
  },
  run_unbuildable: {
    area: runs,
    means:
      "Something the run needs (its dataset version, labeling eval or starting artifact) is gone, so its job can't be built.",
  },
  budget_exhausted: {
    area: runs,
    means: "The run has spent its `max_cost_usd`.",
    fix: "Resume it with a higher cap: `grad runs resume RUN --max-cost-usd N`.",
  },
  queue_limit: {
    area: runs,
    means:
      "The workspace already has the most queued runs, imports and evals it may (`GRAD_MAX_QUEUED_PER_WORKSPACE`, 500 by default). The SDKs don't retry it.",
    fix: "Wait for queued jobs to start, or cancel some, then create the job again.",
  },

  /* -- checkpoints and artifacts -- */
  checkpoint_not_found: {
    area: art,
    means: "No checkpoint with this id, or it has expired.",
    fix: "Best and final checkpoints never expire; others are kept 30 days (`checkpoint_ttl_days`). Promote one to keep it.",
  },
  checkpoint_not_exportable: {
    area: art,
    means:
      "The checkpoint holds training state only; the recipe didn't export it as an artifact.",
    fix: "Promote the run's final artifact, or a checkpoint that has a format.",
  },
  checkpoint_conflict: {
    area: art,
    means:
      "A checkpoint for this step of this attempt already exists with different contents.",
  },
  artifact_not_found: {
    area: art,
    means: "No artifact with this id, `name@version` or `name@latest`.",
  },
  artifact_import_not_found: {
    area: art,
    means: "No artifact import with this id.",
  },
  artifact_pin_not_found: {
    area: art,
    means: "The artifact has no pin for this holder.",
  },
  artifact_pinned: {
    area: art,
    means:
      "The artifact is pinned (on Gradiated Cloud, by a published model version), so it can't be deleted. `artifact.pins` lists the holders.",
    fix: "Unpublish it there first; that removes the pin.",
  },
  artifact_not_servable: {
    area: art,
    means:
      "The artifact can't be served for an eval: it is a reference bundle (the reference trainer's output), or Gradiated Cloud can't serve its format.",
  },
  invalid_format: { area: art, means: "Unknown artifact format." },
  invalid_manifest: {
    area: art,
    means:
      "The bundle's manifest doesn't match the import (for a Hub import, its provenance must name the commit imported).",
  },
  manifest_mismatch: {
    area: art,
    means:
      "The bundle's manifest names a different format or base model from the import's.",
  },
  format_base_mismatch: {
    area: art,
    means:
      "The format and the base model disagree: `encoder_safetensors` needs an encoder base model, every other format a causal LM.",
  },
  name_required: {
    area: art,
    means:
      "An artifact upload needs a `name`. The SDKs default it to the file or directory name.",
  },

  /* -- evals and scoring -- */
  eval_not_found: { area: evals, means: "No eval with this id." },
  empty_eval: {
    area: evals,
    means: "The dataset version has no records with a usable prompt.",
  },
  duplicate_scorer: {
    area: evals,
    means: "Two rubric items have the same name.",
  },
  unknown_judge_model: {
    area: evals,
    means:
      "The judge is neither a priced judge on this server nor an artifact in the workspace.",
    fix: "Self-hosted, operators add judges with `GRAD_JUDGE_MODELS_JSON`; on `grad local up --dev-models` use `test/tiny-judge`.",
  },
  unknown_scorer: {
    area: evals,
    means: "The scorer named isn't one of this eval's code scorers.",
  },
  unknown_eval_output: {
    area: evals,
    means: "A posted score names an output that isn't part of this eval.",
  },
  eval_not_awaiting_scores: {
    area: evals,
    means: "Scores can only be posted while the eval is `awaiting_scores`.",
  },
  eval_not_cancellable: { area: evals, means: "The eval already finished." },
  eval_not_completed: {
    area: evals,
    means: "Results are available once the eval completes.",
    fix: "Wait for it: `ev.wait()` or `grad eval wait EVAL`.",
  },
  inference_unavailable: {
    area: evals,
    means:
      "No inference endpoint is configured for evals (501), or it is unreachable (503). On Gradiated Cloud, evals are coming soon.",
    fix: "Self-hosted, set `GRAD_INFERENCE_BASE_URL` (and `GRAD_JUDGE_BASE_URL`); `grad local up --dev-models` starts a CPU endpoint for the test models.",
  },
  inference_error: {
    area: evals,
    means:
      "The inference or judge endpoint answered with an error; that output records it.",
  },

  /* -- sources and secrets -- */
  source_not_found: { area: src, means: "No source with this id." },
  source_removed: {
    area: src,
    means: "The source was removed, so there is nothing to sync.",
  },
  source_provider_unsupported: {
    area: src,
    means:
      "grad can't sync from this provider; the message lists the ones it can.",
    fix: "Export traces to a file and `grad import` it, or push records with `dataset.push()`.",
  },
  source_secret_required: {
    area: src,
    means: "The provider needs an API key.",
    fix: "Store it with `grad secrets set NAME` and pass `secret=NAME`.",
  },
  source_project_required: {
    area: src,
    means: "Braintrust and PostHog sources need `project`.",
  },
  source_host_required: {
    area: src,
    means:
      "A Phoenix source needs `host`: your Phoenix Cloud space URL or self-hosted Phoenix URL.",
  },
  source_host_invalid: {
    area: src,
    means: "The source host must be an http(s) URL.",
  },
  source_filter_unsupported: {
    area: src,
    means: "This provider has no such filter; the message lists its filters.",
  },
  source_filter_invalid: {
    area: src,
    means: "A filter value has the wrong shape, or `from` isn't before `to`.",
  },
  invalid_schedule: {
    area: src,
    means: "The schedule isn't a five-field UTC cron (`*/15 * * * *`).",
  },
  source_unavailable: {
    area: src,
    means:
      "The `gradiated` source isn't available on this server; it is coming soon on Gradiated Cloud.",
    fix: "Connect your observability tool instead (Langfuse, LangSmith, Braintrust, PostHog, Phoenix).",
  },
  source_upstream_error: {
    area: src,
    means: "The trace provider answered a sync with an error.",
  },
  source_upstream_unavailable: {
    area: src,
    means: "The trace provider couldn't be reached.",
  },
  secret_not_found: {
    area: src,
    means: "No secret with this name in the workspace.",
    fix: "Store it first: `grad secrets set NAME` (the value is read from stdin).",
  },
  secret_in_use: {
    area: src,
    means: "A source uses this secret; the message names it.",
    fix: "Remove the source first.",
  },
  secret_unreadable: {
    area: src,
    means:
      "The source's secret can't be read; the message says why (for example, it was stored under another `GRAD_SECRETS_KEY`).",
    fix: "Set the secret again: `grad secrets set NAME`.",
  },
  secret_host_invalid: {
    area: src,
    means:
      "An `allowed_hosts` entry is neither a host (`host[:port]`) nor a URL.",
  },
  secret_host_not_allowed: {
    area: src,
    means:
      "The secret may not be sent to this host (its `allowed_hosts` don't include it).",
    fix: "Someone with `secrets:write` sets the secret again with `allowed_hosts` naming the host.",
  },
  secrets_unavailable: {
    area: src,
    means: "Workspace secrets aren't configured on this server.",
    fix: "Set `GRAD_SECRETS_KEY` to 32 random bytes in base64 (`openssl rand -base64 32`). The compose file and Helm chart generate one.",
  },

  /* -- server and capacity -- */
  internal_error: {
    area: server,
    means: "An unexpected server error.",
    fix: "Retry (the SDKs do); if it persists, report it with the `request_id`.",
  },
  database_unavailable: {
    area: server,
    means:
      "PostgreSQL is unreachable or overloaded. Sent with `Retry-After: 1`; the SDKs retry.",
  },
  store_unavailable: {
    area: server,
    means:
      "`GET /health/ready`: the training store failed its readiness check.",
  },
  shutting_down: {
    area: server,
    means:
      "`GET /health/ready` on a replica that is draining before it stops, so load balancers send traffic elsewhere.",
    fix: "Nothing to do: retry, and another replica answers.",
  },
  storage_unavailable: {
    area: server,
    means:
      "Object storage (S3) is unreachable or overloaded. Sent with `Retry-After: 1`; the SDKs retry.",
  },

  /* -- Gradiated Cloud -- */
  keys_managed_by_cloud: {
    area: cloud,
    means:
      "With `AUTH_MODE=cloud`, keys are created and revoked in the Gradiated console, not `/v1/keys`.",
  },
  billing_denied: {
    area: cloud,
    means: "The workspace's balance can't cover the run or eval.",
    fix: "Top up, then resume with the same cap.",
  },
  billing_unavailable: {
    area: cloud,
    means:
      "Billing can't be reached, or the price list hasn't refreshed for 24 hours, so new jobs can't be priced.",
  },
  auth_unavailable: {
    area: cloud,
    means:
      "Gradiated Cloud's authentication couldn't be reached to check the key.",
  },
  pin_managed_by_cloud: {
    area: cloud,
    means:
      "The pin belongs to a published model version; it goes away when that version is retired, not through this endpoint.",
  },
  checkpoint_evals_unsupported_on_cloud: {
    area: cloud,
    means:
      "`recipe.evals` (evals of each checkpoint during training) isn't supported on Gradiated Cloud yet.",
    fix: "Drop `recipe.evals` and evaluate `run.artifact` after training.",
  },
};

/* Raised by the SDKs and CLI, not sent by grad-server. */
export const CLIENT_ERROR_DOCS: Record<
  string,
  ErrorDoc & { statuses: number[] }
> = {
  cloud_training_unavailable: {
    area: cloud,
    statuses: [404],
    means:
      "`api.gradiated.com` doesn't serve the training API yet; the SDKs and CLI turn its bare 404 into this error (CLI exit code 6).",
    fix: "Run `grad local up` and `export GRADIATED_PROFILE=local`, or point at your server with `--base-url` or `GRADIATED_BASE_URL`.",
  },
};

export const AREA_ORDER: ErrorArea[] = [
  "Requests and auth",
  "Datasets and imports",
  "Runs and recipes",
  "Checkpoints and artifacts",
  "Evals and scoring",
  "Sources and secrets",
  "Server and capacity",
  "Gradiated Cloud",
];

export const STATUS_MEANING: Record<number, string> = {
  400: "Malformed request",
  401: "Authentication required",
  403: "Forbidden",
  404: "Not found",
  409: "Conflict",
  413: "Payload too large",
  422: "Unprocessable request",
  429: "Too many requests",
  500: "Internal server error",
  501: "Not available on this server",
  502: "Upstream error",
  503: "Dependency unavailable",
};
