import { spawn } from "node:child_process";
import { openSync, closeSync } from "node:fs";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { inject } from "vitest";

import {
  eventually,
  Fatal,
  within,
} from "../../../gateway/test/integration/eventually.js";
import { freePort } from "../../../gateway/test/integration/ports.js";
import { bucket, credentials } from "./s3.js";

export const token = "integration-collector-token-with-at-least-32-characters";

export const startCollector = async () => {
  const runtime = join(
    import.meta.dirname,
    "../../../../../.agents/runtime/collector-integration",
  );
  await mkdir(runtime, { recursive: true });
  const directory = await mkdtemp(join(runtime, "run-"));
  const port = await freePort();
  const admin = await freePort();
  const log = openSync(join(directory, "collector.log"), "w");
  const child = spawn(
    join(import.meta.dirname, "../../target/debug/gradiated-collector"),
    [],
    {
      stdio: ["ignore", log, log],
      env: {
        PATH: process.env.PATH ?? "",
        DATABASE_URL: inject("stack").databaseUrl,
        COLLECTOR_DATA_DIR: join(directory, "spool"),
        COLLECTOR_BUCKET: bucket,
        COLLECTOR_TOKEN: token,
        COLLECTOR_BIND_ADDRESS: `127.0.0.1:${port}`,
        COLLECTOR_ADMIN_ADDRESS: `127.0.0.1:${admin}`,
        COLLECTOR_MAX_BATCH_SECONDS: "1",
        COLLECTOR_DRAIN_SECONDS: "1",
        AWS_ACCESS_KEY_ID: credentials.accessKeyId,
        AWS_SECRET_ACCESS_KEY: credentials.secretAccessKey,
        AWS_REGION: "us-east-1",
        AWS_ENDPOINT_URL_S3: inject("collectorS3Url"),
        AWS_ALLOW_HTTP: "true",
        AWS_EC2_METADATA_DISABLED: "true",
        RUST_LOG: "warn",
      },
    },
  );
  closeSync(log);
  const exited = new Promise<void>((resolve, reject) => {
    child.once("exit", () => resolve());
    child.once("error", reject);
  });
  const close = async () => {
    if (child.exitCode === null && child.signalCode === null) {
      child.kill("SIGTERM");
      if (!(await within(exited, 5_000)).settled) child.kill("SIGKILL");
      await exited;
    }
    await rm(directory, { recursive: true, force: true });
  };

  try {
    await eventually(
      async () => {
        if (child.exitCode !== null || child.signalCode !== null)
          throw new Fatal("collector exited before readiness");
        return (await fetch(`http://127.0.0.1:${admin}/health/ready`)).ok;
      },
      10_000,
      "collector readiness",
    );
  } catch (error) {
    await close();
    throw error;
  }

  return { url: `http://127.0.0.1:${port}/v1/contents`, close };
};
