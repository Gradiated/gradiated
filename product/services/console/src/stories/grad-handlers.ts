import { delay, http, HttpResponse } from "msw";

import type { Run, RunEvent } from "@/lib/grad/types";
import {
  artifact,
  baseModels,
  checkpoints,
  datasets,
  evalFailures,
  evals,
  imports,
  plan,
  records,
  runEvents,
  runs,
  sources,
  usageSummary,
} from "@/stories/grad-fixtures";
import { handlers } from "@/stories/handlers";

const API = "/grad-api/v1";

// Digits do not follow one rule on the wire (`recall_at_10` but `quality_drop_ci95`).
const WIRE_NAMES: Record<string, string> = {
  costPer1kTasksUsd: "cost_per_1k_tasks_usd",
  recallAt1: "recall_at_1",
  recallAt5: "recall_at_5",
  recallAt10: "recall_at_10",
};

const snake = (key: string) =>
  WIRE_NAMES[key] ??
  key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);

// Fixtures use the SDK's camelCase types; the API speaks snake_case. Fixture
// map keys (scores, metrics) are already lowercase, so converting them is a no-op.
export const toWire = (value: unknown): unknown => {
  if (Array.isArray(value)) return value.map(toWire);
  if (typeof value !== "object" || value === null) return value;

  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [snake(key), toWire(item)]),
  );
};

const json = (value: unknown, init?: ResponseInit) =>
  HttpResponse.json(toWire(value) as Record<string, unknown>, init);

const page = <T>(data: readonly T[]) => json({ data, nextCursor: null });

const problem = (status: number, code: string, detail: string) =>
  HttpResponse.json(
    { type: "about:blank", title: code, status, code, detail },
    { status, headers: { "Content-Type": "application/problem+json" } },
  );

const sseFrame = (event: RunEvent) =>
  `id: ${event.seq}\nevent: ${event.type}\ndata: ${JSON.stringify(toWire(event))}\n\n`;

const eventStream = (
  events: readonly RunEvent[],
  after: number,
  finished: boolean,
) => {
  const encoder = new TextEncoder();
  const pending = events.filter(
    (event) => event.type === "completed" || event.seq > after,
  );

  return new HttpResponse(
    new ReadableStream({
      start(controller) {
        for (const event of pending)
          controller.enqueue(encoder.encode(sseFrame(event)));
        if (finished) controller.close();
      },
    }),
    { headers: { "Content-Type": "text/event-stream" } },
  );
};

export interface GradStoryOptions {
  runs?: readonly Run[];
  datasets?: typeof datasets;
  evals?: typeof evals;
  deploy?: "unavailable" | "published";
  planError?: boolean;
  loading?: boolean;
}

export const gradHandlers = ({
  runs: runRows = runs,
  datasets: datasetRows = datasets,
  evals: evalRows = evals,
  deploy = "unavailable",
  planError = false,
  loading = false,
}: GradStoryOptions = {}) => {
  const findRun = (id: unknown) => runRows.find((run) => run.id === id);

  return [
    http.post("/api/v1/workspaces/:workspaceId/training-tokens", () =>
      HttpResponse.json({
        token: "storybook-training-token",
        expires_at: "2030-01-01T00:00:00Z",
      }),
    ),
    http.post("/api/v1/workspaces/:workspaceId/tasks/:task/versions", () =>
      deploy === "published"
        ? HttpResponse.json(
            {
              id: "00000000-0000-4000-8000-0000000000aa",
              name: artifact.version,
              qualification: { outcome: "pending" },
            },
            { status: 201 },
          )
        : HttpResponse.json(
            { code: "not_implemented", detail: "Not implemented" },
            { status: 501 },
          ),
    ),
    http.get(`${API}/runs`, async () => {
      if (loading) await delay("infinite");

      return page(runRows);
    }),
    http.get(`${API}/runs/:id`, ({ params }) => {
      const run = findRun(params.id);

      return run ? json(run) : problem(404, "not_found", "Run not found");
    }),
    http.get(`${API}/runs/:id/events`, ({ params, request }) => {
      const run = findRun(params.id);
      const events = runEvents[String(params.id)] ?? [];
      const after = Number(request.headers.get("Last-Event-ID") ?? 0);

      if (!run) return problem(404, "not_found", "Run not found");
      if (request.headers.get("Accept") === "text/event-stream")
        return eventStream(events, after, events.at(-1)?.type === "completed");

      return json({
        runId: run.id,
        status: run.status,
        data: events,
        nextCursor: null,
        tailCursor: String(events.length),
      });
    }),
    http.get(`${API}/runs/:id/checkpoints`, ({ params }) => {
      const run = findRun(params.id);

      return page(run ? checkpoints(run) : []);
    }),
    http.post(`${API}/runs/:id/cancel`, ({ params }) => {
      const run = findRun(params.id);

      return run
        ? json({ ...run, status: "cancelled" })
        : problem(404, "not_found", "Run not found");
    }),
    http.post(`${API}/runs/:id/resume`, ({ params }) => {
      const run = findRun(params.id);

      return run
        ? json({ ...run, status: "queued", phase: "queued" })
        : problem(404, "not_found", "Run not found");
    }),
    http.post(`${API}/runs/plan`, () =>
      planError
        ? problem(
            422,
            "model_exceeds_gpu_memory",
            "qwen3-32b needs about 96 GB of GPU memory for sft at the recipe defaults; v0 trains on one 80 GB GPU.",
          )
        : json(plan),
    ),
    http.post(`${API}/runs`, () => json(runRows[0])),
    http.get(`${API}/artifacts/:id/download-url`, () =>
      json({
        url: "https://storage.example.com/artifact.grad.tar.gz",
        expiresAt: "2030-01-01T00:00:00Z",
        sha256: artifact.sha256,
        sizeBytes: artifact.sizeBytes,
        filename: `${artifact.name}-${artifact.version}.grad.tar.gz`,
      }),
    ),
    http.get(`${API}/artifacts/:id`, () => json(artifact)),
    http.get(`${API}/base-models`, () => json({ data: baseModels })),
    http.get(`${API}/datasets`, async () => {
      if (loading) await delay("infinite");

      return page(datasetRows);
    }),
    http.get(`${API}/datasets/:name`, ({ params }) => {
      const dataset = datasetRows.find((row) => row.name === params.name);

      return dataset
        ? json(dataset)
        : problem(404, "not_found", "Dataset not found");
    }),
    http.get(`${API}/datasets/:name/records`, ({ params, request }) => {
      const version = Number(
        new URL(request.url).searchParams.get("version") ?? 3,
      );

      return json({
        dataset: params.name,
        version,
        total: version === 3 ? 12_480 : 9_000,
        data: version === 3 ? records : records.slice(0, 4),
        nextCursor: null,
      });
    }),
    http.get(`${API}/sources`, () => page(sources)),
    http.post(`${API}/sources/:id/sync`, () => json(imports[0])),
    http.get(`${API}/imports`, () => page(imports)),
    http.post(`${API}/uploads`, () =>
      json({
        uploadId: "f00d".padEnd(64, "0"),
        method: "PUT",
        url: "/storybook-dataset-upload",
        headers: {
          "Content-Length": "1024",
          "x-amz-checksum-sha256": "storybook",
        },
        expiresAt: "2030-01-01T00:00:00Z",
      }),
    ),
    http.put(
      "/storybook-dataset-upload",
      () => new HttpResponse(null, { status: 200 }),
    ),
    http.post(`${API}/datasets`, () =>
      problem(409, "conflict", "Dataset exists"),
    ),
    http.post(`${API}/datasets/:name/imports`, () =>
      json({ ...imports[0], status: "queued" }),
    ),
    http.get(`${API}/evals`, async () => {
      if (loading) await delay("infinite");

      return page(evalRows);
    }),
    http.get(`${API}/evals/:id`, ({ params }) => {
      const evaluation = evalRows.find((row) => row.id === params.id);

      return evaluation
        ? json(evaluation)
        : problem(404, "not_found", "Eval not found");
    }),
    http.get(`${API}/evals/:id/failures`, ({ params, request }) => {
      const model = new URL(request.url).searchParams.get("model");

      return json({
        evalId: params.id,
        data: evalFailures.filter(
          (outcome) => !model || outcome.model === model,
        ),
        nextCursor: null,
      });
    }),
    http.get(`${API}/usage/summary`, ({ request }) =>
      HttpResponse.json(
        usageSummary(
          new URL(request.url).searchParams.get("group_by") ?? "day",
        ),
      ),
    ),
  ];
};

export const gradStoryHandlers = (options?: GradStoryOptions) => [
  ...gradHandlers(options),
  ...handlers,
];
