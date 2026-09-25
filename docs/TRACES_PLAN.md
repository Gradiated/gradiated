# Traces plan

This plan defines how Gradiated keeps the content of model calls, shows it to
customers as traces, and uses it for training. It replaces the capture and
storage sections of the task fine-tuning contracts and of
[PROXY_FEATURE_PLAN.md](PROXY_FEATURE_PLAN.md) where they differ. See
[Superseded decisions](#superseded-decisions).

## Decisions

| Topic | Decision |
| --- | --- |
| Generation | One model call. Every call gets a `generation_id`: hosted, relayed or imported. |
| `generations` table | ClickHouse usage and billing rows for hosted calls only. It never holds content. |
| Generation content | The request, response and reasoning of one generation. Stored only in S3. |
| Trace | Generations that share a `trace_id`. A grouping, not a stored object. |
| Session | Traces that share a `session_id`. A grouping, not a stored object. |
| Storage | One S3 bucket in `us-east-1`. Batches per workspace, task, hour, retention and trainability; one zstd frame per generation; one manifest per batch. No ClickHouse index. Other regions come later. |
| Retention | A workspace setting of 30, 90 or 180 days. Each object carries a `retention` tag, and a lifecycle rule for each tag deletes it. |
| Trainability | The collector decides it from the source: hosted generations are trainable, relayed ones are not. Each object carries a `trainable` tag. |
| Loss | Best effort, kept simple. Open batches live on local disk and upload after a process restart. Losing a pod or node can lose up to one flush window. |
| Relays | No `generations` row and no billing. Their content is stored like any other generation. |
| Training | Closed-provider outputs are never training targets. Their prompts can be RL inputs and their outputs can be evaluation references. |

## Terms

- **Generation**: one request to one model and its response.
- **Generation content**: everything needed to show or replay one generation.
  The Rust and TypeScript type is `GenerationContent`.
- **Trace**: one unit of customer work, such as one agent run. Customers set
  `x-gradiated-trace-id`. Without it, the trace is the single generation, and
  `trace_id` equals `generation_id`.
- **Session**: a group of traces, such as one conversation. Customers set
  `x-gradiated-session-id`. It is optional.
- **Task**: the customer's label for a kind of work, from `x-gradiated-task`.
  It is nullable. A generation without a task is not stored.

Every header that Gradiated defines uses the `x-gradiated-` prefix, with one
name in every direction.

## Identifiers

- The proxy mints `generation_id` as a UUIDv7 for every request and returns it
  in `x-gradiated-generation-id`.
- For hosted requests the proxy sends the same header to the gateway, which
  uses it as the generation's identifier. The proxy always replaces a value that
  a client sends.
- Imports get new UUIDv7 identifiers. The customer's original identifier is
  kept as `external_id`.
- A UUIDv7 carries its creation time. Point lookups use that time to find the
  batch hour, so no index is necessary.

## Workspace settings

| Setting | Values | Default |
| --- | --- | --- |
| `trace_capture_enabled` | `true`, `false` | `false` |
| `trace_retention_days` | 30, 90, 180 | 30 |

Migration `0007` adds both workspace settings. The proxy reads them with its
identity query and caches them for 15 seconds. Capture requires both
`trace_capture_enabled=true` and a non-empty `x-gradiated-task`. Enabling capture
does not enable automatic training. The gateway will read these settings when
hosted capture is implemented. Writers put `retention_days` in each record. Retention changes apply to new captures only. Existing content keeps the retention
recorded when it was captured. Reads enforce each record's retention; S3 lifecycle
expires batches using their retention tags. The existing worker deletes archived
or deleted workspace prefixes, retries failures and revisits prefixes to catch
buffered collector writes after deletion.

## Generation content record

One JSON object per generation. Keys are sorted. Strings keep their bytes.

```json
{
  "schema": "gradiated.generation-content/1",
  "generation_id": "0199…",
  "workspace_id": "…",
  "task": "support-triage | null",
  "trace_id": "…",
  "session_id": null,
  "external_id": null,
  "source": "hosted | relay | import",
  "provider": "gradiated | anthropic | openai",
  "model": "…",
  "protocol": "openai.chat | openai.responses | anthropic.messages",
  "started_at": "…",
  "completed_at": "…",
  "status": 200,
  "outcome": "complete | error | cancelled | truncated",
  "streamed": true,
  "usage": { "input": 0, "output": 0, "reasoning": 0, "cache_read": 0 },
  "trainable": true,
  "retention_days": 30,
  "raw": { "request": {}, "response": {} },
  "canonical": {
    "version": 1,
    "messages": [],
    "tools": [],
    "params": {},
    "output": { "role": "assistant", "content": "", "reasoning": "", "tool_calls": [] }
  }
}
```

- `raw` is the source of truth. The request is the body as received. A
  streamed response is reassembled into its non-streamed form; SSE bytes are
  not kept.
- `canonical` uses OpenAI Chat message and tool shapes, which RL frameworks and
  chat templates accept. For hosted generations it is the exact request the
  gateway sent to the runtime, with reasoning. It can be rebuilt from `raw`
  when the normaliser changes; `version` records the normaliser. It can be
  `null` until the normaliser for a protocol exists.
- `trainable` must be `true` for `hosted` and `false` for `relay`; the
  collector refuses a record that disagrees. An import is trainable only when
  the customer confirms that the outputs are their own.
- Images, audio and files are recorded as metadata only in version 1.
- Credentials and headers are never stored. The record keeps only the fields
  above.

## Capture points

| Source | Writer | Why |
| --- | --- | --- |
| Hosted | Gateway | It has the runtime request and the reasoning that Messages and Responses clients do not receive. |
| Relay | Proxy | It is the only component that sees the provider exchange. It sends raw bodies; the collector builds `canonical`. |
| Import | API | Customers upload files. |

Capture happens only when the workspace enables it and the request has a task.
Senders do not send generations without a task; if one arrives, the collector
drops it with 204 and counts it as skipped. Each writer copies bytes
into a bounded, non-blocking queue after the response finishes. A full queue or
a refusal from the collector drops the item and counts it. Capture never delays
or fails a customer request. On SIGTERM each writer drains its queue within its
drain window.

## Collector

A Rust service, `product/services/collector`, receives generation content over
HTTP from the proxy, the gateway and the API.

- **Streams**: one open batch per workspace, task, UTC hour of the generation
  identifier, retention and trainability. A generation always lands in its own
  hour's prefix, and a batch has one retention and one trainability.
- **Manifest bounds**: metadata is capped at 64 KiB per generation. A batch also
  seals before its manifest reaches 8 MiB, even when its records compress well.
- **Batches**: each accepted generation is compressed as one zstd frame and
  appended to the stream's open batch, a file on local disk, before the
  collector returns 202. The same bytes become the uploaded batch. An hour
  folder holds many batches.
- **Flush**: when a batch reaches 16 MB or its oldest frame is 60 s old, the
  collector uploads the batch, then its manifest, then deletes the local
  file. A manifest therefore always means its batch is complete. Uploads retry
  with backoff from 1 s to 60 s.
- **Recovery**: at startup the collector cuts a torn final frame and uploads
  every batch left on disk. On SIGTERM it seals every open batch and
  uploads for up to 60 s; what remains uploads at the next start.
- **Storage**: a Deployment with an `emptyDir` volume. The volume survives a
  container restart, so a process crash loses nothing that was accepted. A lost
  pod or node can lose up to one flush window.
- **Limits**: at most 8 requests are handled at once and a record is at most
  32 MiB, which bounds memory; at most 256 batches are open, and the oldest is
  sealed early when a new one is needed; at most 1024 sealed batches wait to
  upload; batch bytes on disk have a cap. At a cap the collector returns 503
  and the sender drops the record.
- **Replicas**: each replica writes its own batches; the replica name is part
  of the batch name. Replicas do not coordinate.
- **Idempotency**: an upload retry writes the same object key, so a batch is
  never stored twice. A sender retry can store a generation twice; its
  `generation_id` is unique, so every reader keeps the first frame for an
  identifier.

## Relay wire contract

The proxy sends `application/x-ndjson` to `POST /v1/contents`. Each non-empty
line is either a `GenerationContent` record or the following relay envelope:

```json
{
  "schema": "gradiated.relay/1",
  "generation_id": "UUIDv7",
  "workspace_id": "UUID",
  "task": "support-triage",
  "trace_id": null,
  "session_id": null,
  "provider": "anthropic",
  "path": "/v1/messages",
  "retention_days": 30,
  "status": 200,
  "outcome": "complete",
  "completed_at": "2026-09-25T12:00:00Z",
  "request": "{\"model\":\"synthetic-model\",\"messages\":[]}",
  "response_content_type": "application/json",
  "response": "{\"content\":[],\"usage\":{\"input_tokens\":0,\"output_tokens\":0}}"
}
```

The proxy copies unencoded UTF-8 request and response text and never parses
provider protocols. Encoded responses or invalid UTF-8 bodies are skipped and
counted as `unsupported`; the client receives the original bytes. The envelope
contains no credentials or header collections. `outcome` is `complete`, `error`,
`cancelled` or `truncated`. The collector derives `started_at` from UUIDv7,
`model` from the request, and `protocol` from provider and path. A missing trace
identifier defaults to the generation identifier. Relay records always have
`source=relay`, `trainable=false` and `canonical=null`.

For JSON responses, `raw.request` and `raw.response` contain parsed JSON. For
SSE, the collector rebuilds Anthropic Messages, OpenAI Chat and OpenAI Responses
into their non-streaming JSON shapes. Text, reasoning and tool arguments are
assembled; Responses terminal events supply the authoritative response snapshot.
Supported interrupted streams retain the assembled partial response and the
sender's outcome. A malformed stream, incomplete Anthropic tool JSON or an
unsupported partial event is rejected as an invalid line instead of storing a
misleading complete response. Provider usage remains in `raw.response`; the
record's usage maps input, output, reasoning and cached input tokens, with null
for unavailable counts. Canonical messages are deferred to a later change.

The request body is capped at 32 MiB, as for single-record intake. Each line is
validated and appended independently. Invalid lines are dropped and counted;
records without a task are skipped and counted. A processed batch returns 202,
even if every line was dropped. A spool refusal returns 503 for the batch;
earlier lines can already be stored, so readers deduplicate by `generation_id`.
Authentication and request-size errors still return 401 and 413. Single JSON
intake keeps its 202, 204 and 400 behavior.

Protocol references: [Anthropic streaming](https://platform.claude.com/docs/en/build-with-claude/streaming)
and [OpenAI Responses streaming](https://platform.openai.com/docs/api-reference/responses-streaming).

## S3 layout

```text
s3://gradiated-prod-contents-us-east-1-<account>/v1/ws=<workspace_id>/task=<task_key>/dt=<YYYY-MM-DD>/hr=<HH>/<replica>-<batch_id>.jsonl.zst
                                                                                          .../<replica>-<batch_id>.manifest.json
```

- `task_key` is the task label when it matches `[a-z0-9_-]{1,64}`, otherwise a
  hash of it.
- The manifest (`gradiated.generation-content-manifest/1`) lists, for each
  generation, the record's metadata fields (everything except `raw` and
  `canonical`) with the frame's `offset` and `length`.
- Every batch and manifest has two tags: `retention=30d|90d|180d` and
  `trainable=true|false`.
- The bucket has its own KMS key, blocks public access, and refuses requests
  without TLS. The bucket has a lifecycle rule for each of 7, 14, 30, 60, 90,
  180 and 365 days, matched by the object's `retention` tag; the product offers
  30, 90 and 180 today, and can change within that set without an
  infrastructure change. A backstop rule deletes any object after 365 days.
- The keys are Hive-style: each `name=value` level becomes a column in DuckDB,
  Athena, Spark and Hugging Face `datasets`, and filters on those columns skip
  the folders that cannot match.

Workspace capture and retention fields are updated through
`PATCH /api/v1/workspaces/{workspace_id}`.
Only supplied fields change; the response is the updated workspace. Workspace
archival uses `DELETE` on the same resource.

## Read paths

- **Traces list**: the Management API authorizes workspace membership and reads
  manifests for an exact task, newest hour first. Pages contain at most 100
  manifest rows, with cursors within a manifest and across hours. Empty pages may
  have a continuation after a bounded scan of up to 24 empty pages. The console deduplicates generation IDs across loaded
  pages and groups them by `trace_id`; trace counts describe loaded content only.
  The task Data tab reads `GET .../workspaces/{workspace_id}/generations?task_id=...`.
  `task_id` is the URL-encoded exact capture-header value. There is no separate
  task-discovery endpoint. Date-range filters on the same collection retain the
  hosted usage-log view; task filters return captured metadata. Mixing those
  filter sets is rejected, rather than silently ignoring a filter.
  Other training, model and evaluation UI remains mocked until those features ship.
- **One generation**: `GET .../generations/{generation_id}?content_ref=...`
  uses the opaque manifest reference returned by the list. The API
  checks workspace membership, the reference's workspace prefix, the manifest
  row's workspace and generation ID, and retention before a range GET of the
  compressed frame. Decoded content is checked again and responses use no-store.
  Only the selected generation is downloaded when opening a trace.
- **One trace**: the API reads the manifests around the trace's first
  generation and merges rows from adjacent batches.
- **Export**: one JSONL line per trace, with its generations in order. The same
  format is accepted by import.
- **Training**: the dataset builder reads prefixes and manifests, freezes the
  input manifest for a run, and writes Parquet under `runs/<run_id>/dataset/`.
  Only objects tagged `trainable=true` supply training targets.
- **Analysis**: DuckDB reads batches directly, for example
  `read_json('s3://…/v1/ws=*/task=*/dt=*/hr=*/*.jsonl.zst', hive_partitioning = true)`.
  The manifests are smaller and hold the metadata columns.

Each reader gets its own role that can read the bucket and decrypt with its
key. The collector's role can only write.

## Import

- Each source format has one mapping into the record: `canonical` from the
  source's messages, `raw` as the source row, `source = "import"` and
  `protocol` naming the format.
- First formats: the export format above, OpenAI chat JSONL
  (`{"messages": [], "tools": []}`), and CSV with a column mapping.
- The API validates each line and sends it to the collector, which writes it
  like any other generation.

## Deletion and residency

- Deleting a non-default workspace archives it and disables capture immediately.
  Content reads are denied at once. The existing worker removes the workspace
  prefix asynchronously, retries partial failures, and catches late flushes.
  The API role reads/decrypts content; the worker can list/delete but cannot read
  or decrypt it. Capture/retention changes and deletion require owner/admin access.
- Version 1 has one bucket, in `us-east-1`. Other regions add a bucket, a
  collector deployment per region, and a region field on the workspace that
  selects them.
- ClickHouse holds no generation content, so it does not change residency.

## Observability

Collector metrics: generations accepted and rejected (by reason), batches and
bytes uploaded, upload failures, batches recovered at startup, open streams and
batch bytes on disk. Collector alerts: telemetry missing, unavailable, uploads
failing for about 2 minutes, disk above 80% of its cap, and rejections. Writers add a
dropped-capture counter and a simple threshold alert for sustained drops.

## Build sequence

1. **Collector**: HTTP intake, batches, flush, recovery, manifests, tagged S3
   upload, metrics. Terraform for the bucket and the IAM role. The Deployment,
   alerts and dashboard.
2. **Proxy capture**: the workspace settings, the capture queue for relays, raw
   bodies to the collector, and raw response reconstruction for Chat, Responses
   and Messages. Canonical normalization follows separately.
3. **Gateway capture**: hosted content with the runtime request and reasoning.
4. **Read API and console**: traces list, trace detail and generation lookup
   from manifests.
5. **Import and export**.
6. **Training input**: dataset builder reads prefixes and manifests.

## Superseded decisions

- The ClickHouse `traces` table in
  [TASK_FINE_TUNING_FROM_TRACES_PLAN.md](TASK_FINE_TUNING_FROM_TRACES_PLAN.md),
  [TASK_FINE_TUNING_GATEWAY_CONTRACT.md](TASK_FINE_TUNING_GATEWAY_CONTRACT.md)
  and [TASK_FINE_TUNING_OPERATIONS_CONTRACT.md](TASK_FINE_TUNING_OPERATIONS_CONTRACT.md):
  generation content lives in S3 and no table holds it.
- Relay generation rows and the relay usage record (build step 4 of the proxy
  plan): relays have no `generations` row.
- The rejection of S3 and batched storage for traces.
- The `traces` exclusion and zero-retention statement in
  [DATA_MODEL.md](DATA_MODEL.md).

## Open questions

- The price of 90-day and 180-day retention.
- Trace detection for clients that do not send `x-gradiated-trace-id`: the
  W3C `traceparent` header and other known client headers first, then
  inference by matching a request's messages to an earlier generation's
  messages and output. A `trace_source` field can record which method set the
  trace.
- Regions other than `us-east-1`.
- Provider list prices for the cost column of relayed generations.
