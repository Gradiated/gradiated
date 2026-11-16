# Collector

The collector receives generation content from the proxy, the gateway and the
API, and stores it in S3 batches. [TRACES_PLAN.md](../../../docs/TRACES_PLAN.md)
owns the design.

## Contract

`POST /v1/contents` with `Authorization: Bearer $COLLECTOR_TOKEN` and one
`gradiated.generation-content/1` JSON record as the body. `retention_days` must
be 30, 90 or 180, and `trainable` must be `true` for `hosted` and `false` for
`relay`. The proxy also sends NDJSON `gradiated.hosted/1` and
`gradiated.relay/1` envelopes with raw JSON or SSE response bodies. The collector
normalizes them into generation records. Hosted Chat Completions include a
canonical prompt and answer; length-limited answers are marked truncated.

| Status | Meaning                                                                                                               |
| ------ | --------------------------------------------------------------------------------------------------------------------- |
| 202    | The record is written to disk and will be uploaded.                                                                   |
| 204    | The record has no task, so it is not stored.                                                                          |
| 400    | The body is not a valid contents record.                                                                              |
| 401    | The token is missing or wrong.                                                                                        |
| 413    | The body is larger than `COLLECTOR_MAX_RECORD_BYTES`.                                                                 |
| 503    | The memory or disk budget is full, or the collector is shutting down. The sender retries once, then drops the record. |

Generation metadata (all fields copied into manifests) is capped at 64 KiB per
record. Batches also seal before their manifest reaches 8 MiB, independently of
compressed batch size. This bounds uploader memory and keeps manifest reads
within the API budget. Raw request/response bodies retain the existing limit.

The admin port serves `/health/live`, `/health/ready` and `/metrics`.

## Storage

Each workspace, task, generation hour, retention and trainability has one open
batch: a file on local disk holding a sequence of zstd frames, one per
generation. The collector returns 202 after the frame is written to that file.
The same bytes become the uploaded batch. An hour folder in S3 holds many
batches.

A batch is sealed at `COLLECTOR_MAX_BATCH_BYTES` or
`COLLECTOR_MAX_BATCH_SECONDS`, uploaded, then its manifest is uploaded, and
the file is deleted. Both objects are tagged `retention=<days>d` and
`trainable=<true|false>`. At startup the collector cuts any torn final frame and
uploads every batch left on disk. Capture is best effort: a lost pod or node
can lose up to one flush window.

```text
v1/ws=<workspace>/task=<task>/dt=<YYYY-MM-DD>/hr=<HH>/<replica>-<batch>.jsonl.zst
v1/ws=<workspace>/task=<task>/dt=<YYYY-MM-DD>/hr=<HH>/<replica>-<batch>.manifest.json
```

`zstd -d` on a batch gives JSON Lines. Each manifest row has the byte `offset`
and `length` of its frame, so one generation can be read with a range request.

## Task registration

With `DATABASE_URL` configured, intake queues one registration per workspace and
task name on local disk. A background worker inserts tasks idempotently and uses
PostgreSQL's default training cron. Conflicts preserve the existing task ID,
models and schedule. A cache of up to 10,000 recently seen registrations expires
after one hour to avoid writes on every trace.

PostgreSQL availability does not affect intake, readiness or S3 uploads. Failed
registrations retry every minute; the local queue survives process restarts.
Recovered trace batches also enqueue their tasks before being deleted. The queue
shares the collector spool's local-volume lifetime: losing that volume can lose
pending registrations as well as captured traces. Empty and dot-segment names
are not registered. Historical S3-only tasks are not automatically backfilled.

Production currently uses the database-only worker Secret and its existing login.
Remote PostgreSQL connections require verified TLS with `DATABASE_CA_BUNDLE_PATH`.
Without `DATABASE_URL`, standalone capture still works but registers no tasks.
Metrics expose `gradiated_collector_tasks_registered_total` and
`gradiated_collector_task_registration_failures_total`.

## Compressed bodies

The proxy captures compressed request and response bodies as sent, with their
`Content-Encoding`. The collector decodes `gzip`, `x-gzip`, `deflate` (zlib or
raw), `br` and `zstd`, including stacked codings, with a 96 MiB output limit
against decompression bombs, then parses the decoded body like any other. A
cancelled or failed stream keeps what decoded before it ended. A body that does
not decode, or another coding, is stored raw with `raw.request_content_encoding`
or `raw.response_content_encoding` naming the coding that still applies.

## Scaling

KEDA scales the collector from 3 to 12 replicas
([`collector-autoscaling.yaml`](../../../infra/environments/prod/us-east-1/kubernetes/workloads/collector-autoscaling.yaml)).
The demand is `gradiated_collector_requests_in_flight`, intake requests being
handled or waiting for one of the 8 slots, at 4 per pod, alongside CPU and
memory. Proxies find every replica through the `collector-headless` Service and
spread posts across them, so a new replica takes traffic within 5 seconds. Scale
down removes one pod every 5 minutes; the pod stops taking posts, then seals and
uploads its open batches within `COLLECTOR_DRAIN_SECONDS`.

## Configuration

| Variable                            | Default        | Purpose                                                                       |
| ----------------------------------- | -------------- | ----------------------------------------------------------------------------- |
| `DATABASE_URL`                      | none           | PostgreSQL task registration; set in local and production deployments         |
| `DATABASE_CA_BUNDLE_PATH`           | none           | RDS CA bundle for a remote PostgreSQL connection                              |
| `COLLECTOR_DATA_DIR`                | required       | Directory for batch files                                                     |
| `COLLECTOR_BUCKET`                  | none           | S3 bucket; region and credentials come from the AWS environment               |
| `COLLECTOR_LOCAL_STORE_DIR`         | none           | Local directory instead of S3, for development                                |
| `COLLECTOR_TOKEN`                   | required       | Shared bearer token, at least 32 characters                                   |
| `COLLECTOR_REPLICA`                 | `HOSTNAME`     | Batch name prefix, unique per replica                                         |
| `COLLECTOR_BIND_ADDRESS`            | `0.0.0.0:3004` | Intake listener                                                               |
| `COLLECTOR_ADMIN_ADDRESS`           | `0.0.0.0:9004` | Health and metrics                                                            |
| `COLLECTOR_MAX_RECORD_BYTES`        | `100663296`    | Largest record: a 32 MB request and its response, binary bodies in base64     |
| `COLLECTOR_MAX_BUFFERED_BYTES`      | `268435456`    | Request bodies held at once; a post that does not fit gets 503 `busy`         |
| `COLLECTOR_MAX_CONCURRENT_REQUESTS` | `8`            | Requests handled at once                                                      |
| `COLLECTOR_MAX_OPEN_STREAMS`        | `256`          | Open batches before the oldest is sealed early                                |
| `COLLECTOR_MAX_PENDING_BATCHES`     | `1024`         | Sealed batches waiting to upload before records that need a new batch get 503 |
| `COLLECTOR_MAX_BATCH_BYTES`         | `16777216`     | Batch size that triggers upload                                               |
| `COLLECTOR_MAX_BATCH_SECONDS`       | `60`           | Batch age that triggers upload                                                |
| `COLLECTOR_DISK_CAP_BYTES`          | `8589934592`   | Batch bytes on disk before new records get 503                                |
| `COLLECTOR_DRAIN_SECONDS`           | `60`           | Upload time allowed at shutdown                                               |

## Local run

`pnpm dev` from `product/` starts this service natively and SeaweedFS in Compose.
The collector uses the same S3 upload path as production, with local credentials,
`AWS_ENDPOINT_URL_S3=http://127.0.0.1:8333` and `AWS_ALLOW_HTTP=true`. The bucket
is provisioned automatically. See the [local stack](../../README.md#api-development)
and run `pnpm smoke:capture` to verify uploads, tags and range reads.

For standalone filesystem-only development:

```sh
COLLECTOR_DATA_DIR=/tmp/collector COLLECTOR_LOCAL_STORE_DIR=/tmp/contents \
COLLECTOR_TOKEN=local-development-token-0123456789 cargo run
```

The intake also accepts `application/x-ndjson` containing generation content or
`gradiated.relay/1` lines. Invalid lines are counted and dropped independently;
a spool write refusal returns 503, so retrying senders may duplicate earlier
lines. Readers deduplicate by generation ID. Relay parsing and SSE reconstruction
live here; the proxy sends raw text. See the relay wire contract in
[TRACES_PLAN.md](../../../docs/TRACES_PLAN.md).

## Tests

From `product/`, run `pnpm --filter @gradiated/collector check` for Rust component
tests and TypeScript checks. `pnpm --filter @gradiated/collector test:integration`
builds the collector, proxy and gateway, then starts disposable PostgreSQL,
Valkey and SeaweedFS containers on local ports. It checks JSON and streamed relay
capture, cancellation, error records, object tags, range reads and task registration.
No provider credentials or production endpoints are used.

The Rust partial-upload test checks that a failed manifest upload preserves the
spool, shutdown stops retries at its deadline, and restart reuses the data and
manifest keys. Permission-failure tests must run without root's DAC bypass.
Both suites run in the product CI workflow; storage integration is a required
dependency of `Product tests passed`.
