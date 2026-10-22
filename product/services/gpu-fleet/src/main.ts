import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import { createControlDatabase, syncFleetInstances } from "@gradiated/control";
import { z } from "zod";

import { credentialedSync } from "./database.js";
import { createFleet } from "./fleet.js";
import { inClusterKubernetes } from "./kubernetes.js";
import { createLease } from "./lease.js";
import { createMetrics } from "./metrics.js";
import { pingHost } from "./observe.js";

const config = z
  .object({
    POD_NAME: z.string().min(1),
    NAMESPACE: z.literal("gpu-inference"),
    HOST_KEYS_DIRECTORY: z.string().min(1),
    DATABASE_URL_FILE: z.string().min(1),
    // Comma-separated provider/accountId pairs whose instance rows the fleet owns.
    FLEET_ACCOUNTS: z
      .string()
      .transform((value) => value.split(",").map((item) => item.trim()))
      .pipe(z.array(z.string().regex(/^[a-z][a-z0-9_-]*\/[^/\s]+$/)).min(1)),
    METRICS_PORT: z.coerce.number().int().min(1).max(65535).default(9090),
    RECONCILE_SECONDS: z.coerce.number().int().min(5).default(30),
    SYNC_SECONDS: z.coerce.number().int().min(30).default(300),
  })
  .parse(process.env);

const log = (event: Record<string, unknown>) =>
  process.stdout.write(
    JSON.stringify({
      timestamp: new Date().toISOString(),
      level: "info",
      ...event,
    }) + "\n",
  );

const credential = credentialedSync(
  () => {
    try {
      return readFileSync(config.DATABASE_URL_FILE, "utf8").trim() || undefined;
    } catch {
      return undefined;
    }
  },
  (url) => {
    const { database, pool } = createControlDatabase(url, 2);
    return { database, close: () => pool.end() };
  },
  (database) => (hosts, beforeCommit) =>
    syncFleetInstances(database, hosts, {
      accounts: config.FLEET_ACCOUNTS,
      beforeCommit,
    }),
);

const LEASE_SECONDS = 60;
// Writes stop this long before the lease could expire, leaving room for clock
// skew and a slow renewal.
const WRITE_MARGIN_MS = 20_000;
let leaseValidUntil = 0;
const leading = () => Date.now() < leaseValidUntil;

const api = inClusterKubernetes();
const metrics = createMetrics();
const fleet = createFleet({
  api,
  metrics,
  ping: (instanceId) => pingHost(instanceId, config.HOST_KEYS_DIRECTORY),
  sync: credential.resolve,
  leading,
  log,
});
const lease = createLease({
  api,
  namespace: config.NAMESPACE,
  name: "gpu-fleet",
  identity: config.POD_NAME,
  durationSeconds: LEASE_SECONDS,
});

const server = createServer(async (request, response) => {
  if (request.url === "/healthz") return response.end("ok");
  if (request.url === "/metrics") {
    response.setHeader("content-type", metrics.registry.contentType);
    return response.end(await metrics.registry.metrics());
  }
  response.statusCode = 404;
  response.end();
});
server.listen(config.METRICS_PORT);

let stopping = false;
const stop = async () => {
  stopping = true;
  leaseValidUntil = 0;
  await lease.release().catch(() => undefined);
  await credential.close();
  server.close();
  process.exit(0);
};
process.on("SIGTERM", () => void stop());
process.on("SIGINT", () => void stop());

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// Reconcile and sync run on their own timers, so a slow PostgreSQL query cannot
// hold up Service reconciliation.
const every = async (seconds: number, pass: () => Promise<void>) => {
  while (!stopping) {
    if (leading()) await pass();
    await sleep(seconds * 1000);
  }
};

const renew = async () => {
  let led = false;
  while (!stopping) {
    const started = Date.now();
    const acquired = await lease.acquire().catch((error: unknown) => {
      log({ event: "gpu_fleet_lease_failed", error: (error as Error).message });
      return false;
    });
    leaseValidUntil = acquired
      ? started + LEASE_SECONDS * 1000 - WRITE_MARGIN_MS
      : 0;
    metrics.leader.set(acquired ? 1 : 0);
    if (led && !acquired) fleet.standDown();
    led = acquired;
    await sleep(5_000);
  }
};

await Promise.all([
  renew(),
  every(config.RECONCILE_SECONDS, fleet.reconcile),
  every(config.SYNC_SECONDS, fleet.syncDatabase),
]);
