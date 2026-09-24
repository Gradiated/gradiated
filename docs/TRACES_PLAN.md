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
| Contents | The request, response and reasoning of one generation. Stored only in S3. |
| Trace | Generations that share a `trace_id`. A grouping, not a stored object. |
| Session | Traces that share a `session_id`. A grouping, not a stored object. |
| Storage | Regional S3 buckets. Batches per workspace and task, one zstd frame per generation, one manifest per batch. No ClickHouse index. |
| Retention | 30 days by S3 lifecycle rule. Per-workspace retention later, by object tag. |
| Loss | Best effort, but a crash must not lose accepted contents. Open batches live on disk and upload after a restart. |
| Relays | No `generations` row and no billing. Their contents are stored like any other generation. |
| Training | Closed-provider outputs are never training targets. Their prompts can be RL inputs and their outputs can be evaluation references. |

## Terms

- **Generation**: one request to one model and its response.
- **Contents**: everything needed to show or replay one generation. The word
  is also the S3 prefix and the Rust and TypeScript type name
  (`GenerationContents`).
- **Trace**: one unit of customer work, such as one agent run. Customers set
  `x-gradiated-trace-id`. Without it, the trace is the single generation, and
  `trace_id` equals `generation_id`.
- **Session**: a group of traces, such as one conversation. Customers set
  `x-gradiated-session-id`. It is optional.
- **Task**: the customer's label for a kind of work, from `x-gradiated-task`.

## Identifiers

- The proxy mints `generation_id` as a UUIDv7 for every request at the front
  door and returns it in `x-generation-id`.
- For hosted requests the proxy sends the identifier to the gateway in
  `x-gradiated-generation-id`. The gateway uses it as the generation's
  identifier. The proxy always replaces a value that a client sends.
- Imports get new UUIDv7 identifiers. The customer's original identifier is
  kept as `external_id`.
- A UUIDv7 carries its creation time. Point lookups use that time to find the
  batch hour, so no index is necessary.

## Contents record

One JSON object per generation. Keys are sorted. Strings keep their bytes.

```json
{
  "schema": "gradiated.contents/1",
  "generation_id": "0199…",
  "workspace_id": "…",
  "task": "support-triage",
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
  "trainable": false,
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
  when the normaliser changes; `version` records the normaliser.
- `trainable` is false for relays and for imports that contain closed-provider
  outputs.
- Images, audio and files are recorded as metadata only in version 1.
- Credentials and headers are never stored. The record keeps only the fields
  above.

## Capture points

| Source | Writer | Why |
| --- | --- | --- |
| Hosted | Gateway | It has the runtime request and the reasoning that clients do not receive. |
| Relay | Proxy | It is the only component that sees the provider exchange. It sends raw bodies; the collector builds `canonical`. |
| Import | API | Customers upload JSONL. |

Capture happens only when the workspace enables it and the request has a task
label. Each writer copies bytes into a bounded, non-blocking queue after the
response finishes. A full queue drops the newest item and counts it. Capture
never delays or fails a customer request. On SIGTERM each writer drains its
queue within its drain window.

## Collector

A Rust service, `product/services/collector`, receives contents over HTTP from
the proxy, the gateway and the API.

- **Streams**: one open batch per region, workspace, task and UTC hour of the
  generation identifier. A generation always lands in its own hour's prefix.
- **Write-ahead**: each accepted generation is compressed as one zstd frame
  and appended to the stream's segment file on local disk before the collector
  acknowledges it. The segment file is the batch.
- **Flush**: when a segment reaches 64 MB or its oldest frame is 60 s old, the
  collector uploads the segment and its manifest, then deletes the local files.
  Quiet streams can use a longer interval to save requests.
- **Recovery**: at startup the collector uploads every segment left on disk.
  A torn final frame is cut off at the last complete frame.
- **Storage**: a StatefulSet with one EBS volume per replica, so segments
  survive pod restarts and rescheduling in the same zone.
- **Memory**: bounded by the intake queue and one small header per open
  stream. Frame bytes go to disk, not to memory buffers. When total disk use
  reaches its cap, the collector flushes the largest open segment early. When
  it cannot flush, it refuses new contents with 503 and the writers drop them.
- **Replicas**: each replica writes its own batches; the replica name is part
  of the batch name. Replicas do not coordinate.
- **Idempotency**: a writer that retries sends the same `generation_id`.
  Readers keep the first frame for an identifier.

## S3 layout

```text
s3://gradiated-<env>-contents-<region>/v1/ws=<workspace_id>/task=<task_key>/dt=<YYYY-MM-DD>/hr=<HH>/<replica>-<batch_id>.jsonl.zst
                                                                                      .../<replica>-<batch_id>.manifest.json
```

- `task_key` is the task label when it matches `[a-z0-9_-]{1,64}`, otherwise a
  hash of it.
- The manifest lists, for each generation: `generation_id`, `trace_id`,
  `session_id`, `model`, `provider`, `source`, `trainable`, `started_at`,
  `completed_at`, `usage`, `offset` and `length`.
- Buckets are encrypted with a KMS key per region, block public access, and
  have a lifecycle rule that deletes objects after 30 days.
- The Hive-style keys let DuckDB, Athena, Spark and Hugging Face `datasets`
  read the data without an index.

## Read paths

- **Traces list**: the console reads the newest manifests for a workspace and
  task, groups rows by `trace_id`, and pages back in time. It does not sort or
  filter across all 30 days.
- **One generation**: `generation_id` gives the exact hour. The API reads that hour's
  manifests for the workspace, then fetches the frame with a range GET.
- **One trace**: the API reads the manifests around the trace's first
  generation and merges rows from adjacent batches.
- **Export**: one JSONL line per trace, with its generations in order. The same
  format is accepted by import.
- **Training**: the dataset builder reads prefixes and manifests, freezes the
  input manifest for a run, and writes Parquet under `runs/<run_id>/dataset/`.

## Import

- Accepted formats: the export format above, and OpenAI chat fine-tuning JSONL
  (`{"messages": [], "tools": []}`).
- Imported generations have `source = "import"` and `trainable = false` unless
  the customer confirms that the outputs are their own.
- The API validates each line and sends it to the collector, which writes it
  like any other generation.

## Deletion and residency

- Workspace deletion removes the workspace prefix in each regional bucket.
- A workspace's region selects its bucket. Version 1 has one region,
  `us-east-1`; EU storage adds a bucket and a region field on the workspace.
- ClickHouse holds no contents, so it does not change residency.

## Observability

Metrics: generations accepted, dropped (by reason) and flushed; segment bytes on
disk; flush latency; upload failures; recovery uploads at startup. Alerts:
upload failures for 5 minutes, disk above 80% of its cap, and a writer drop rate
above 1% for 10 minutes.

## Build sequence

1. **Collector**: HTTP intake, segment write-ahead, flush, recovery, manifests,
   S3 upload, metrics. Terraform for the buckets and the IAM role. Tests with a
   local S3 double and forced crashes.
2. **Proxy capture**: identifier forwarding, capture queue for relays, raw
   bodies to the collector, `canonical` built in the collector for Chat,
   Responses and Messages.
3. **Gateway capture**: the proxy's identifier, hosted contents with the runtime
   request and reasoning.
4. **Read API and console**: traces list, trace detail and generation lookup
   from manifests.
5. **Import and export**.
6. **Training input**: dataset builder reads prefixes and manifests.

## Superseded decisions

- The ClickHouse `traces` table in
  [TASK_FINE_TUNING_FROM_TRACES_PLAN.md](TASK_FINE_TUNING_FROM_TRACES_PLAN.md),
  [TASK_FINE_TUNING_GATEWAY_CONTRACT.md](TASK_FINE_TUNING_GATEWAY_CONTRACT.md)
  and [TASK_FINE_TUNING_OPERATIONS_CONTRACT.md](TASK_FINE_TUNING_OPERATIONS_CONTRACT.md):
  contents live in S3 and no table holds them.
- Relay generation rows and the relay usage record (build step 4 of the proxy
  plan): relays have no `generations` row.
- The rejection of S3 and batched storage for traces.
- The `traces` exclusion and zero-retention statement in
  [DATA_MODEL.md](DATA_MODEL.md).

## Open questions

- The per-workspace setting for capture, and whether it also enables automatic
  training.
- Retention per customer, and its price.
- Whether the collector should infer traces for clients that do not send
  `x-gradiated-trace-id`, by matching a request's messages to an earlier
  generation's messages and output.
- Provider list prices for the cost column of relayed generations.
