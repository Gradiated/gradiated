import { createServer } from "node:http";
import { Registry } from "prom-client";
import { TrainingMetrics } from "./training/metrics.js";
import {
  createContentStore,
  createControlDatabase,
  readTrainingMetrics,
} from "@gradiated/control";
import { Runtime } from "@temporalio/worker";
import { parseTemporalWorkerEnvironment } from "./environment.js";
import { runTrainingWorker } from "./training/worker.js";

const environment = parseTemporalWorkerEnvironment(process.env);
Runtime.install({
  telemetryOptions: {
    metrics: {
      prometheus: {
        bindAddress: `0.0.0.0:${environment.METRICS_PORT}`,
        countersTotalSuffix: true,
        unitSuffix: true,
        useSecondsForDurations: true,
      },
    },
  },
});

const abortController = new AbortController();
let ready = false;
const shutdown = () => {
  ready = false;
  abortController.abort();
};
for (const signal of ["SIGINT", "SIGTERM"] as const)
  process.once(signal, shutdown);

const { database, pool } = createControlDatabase(environment.DATABASE_URL, 5);
pool.on("error", () => {
  console.error(
    JSON.stringify({
      service: "temporal-worker",
      event: "postgres_connection_failed",
    }),
  );
  process.exitCode = 1;
  shutdown();
});

const registry = new Registry();
const trainingMetrics = new TrainingMetrics(registry, () =>
  readTrainingMetrics(database),
);

const health = createServer(async (request, response) => {
  if (request.url === "/metrics") {
    void trainingMetrics.collect();
    response.writeHead(200, { "content-type": registry.contentType });
    response.end(await registry.metrics());
    return;
  }
  if (request.url === "/healthz" || request.url === "/readyz") {
    response.writeHead(request.url === "/healthz" || ready ? 200 : 503);
    response.end();
    return;
  }
  response.writeHead(404).end();
});
health.on("error", () => {
  process.exitCode = 1;
  shutdown();
});
health.listen(environment.PORT, "0.0.0.0");

try {
  await runTrainingWorker({
    database,
    contents: createContentStore(environment.CONTENTS_BUCKET),
    environment: process.env,
    signal: abortController.signal,
    onReady: async () => {
      ready = true;
    },
  });
} catch {
  console.error(
    JSON.stringify({ service: "temporal-worker", event: "worker_failed" }),
  );
  process.exitCode = 1;
} finally {
  shutdown();
  health.close();
  await pool.end();
  await Runtime.instance().shutdown();
}
