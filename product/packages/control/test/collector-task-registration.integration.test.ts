import { execFile, spawn, type ChildProcess } from "node:child_process";
import { once } from "node:events";
import { mkdtemp, readdir, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { eq } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";
import { afterAll, beforeAll, expect, it } from "vitest";

import { tasks, workspaces } from "../src/db/schema/index.js";
import { seedMember } from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

const collector = fileURLToPath(
  new URL("../../../services/collector/", import.meta.url),
);
const execute = promisify(execFile);
const token = "local-test-token-with-at-least-32-characters";
let db: TestDatabase;

beforeAll(async () => {
  await execute(
    "cargo",
    ["build", "--locked", "--manifest-path", join(collector, "Cargo.toml")],
    { timeout: 180_000 },
  );
  db = await createTestDatabase();
}, 190_000);
afterAll(async () => {
  await db?.dispose();
});

const waitFor = async (predicate: () => Promise<boolean>) => {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error("Collector condition did not become ready.");
};

const freePort = async () => {
  const socket = createServer();
  socket.listen(0, "127.0.0.1");
  await once(socket, "listening");
  const address = socket.address();
  if (!address || typeof address === "string")
    throw new Error("Missing test port.");
  await new Promise<void>((resolve, reject) =>
    socket.close((error) => (error ? reject(error) : resolve())),
  );
  return address.port;
};

const start = async (directory: string, databaseUrl: string) => {
  const port = await freePort();
  const admin = await freePort();
  const process: ChildProcess = spawn(
    join(collector, "target/debug/gradiated-collector"),
    [],
    {
      env: {
        PATH: globalThis.process.env.PATH,
        DATABASE_URL: databaseUrl,
        COLLECTOR_DATA_DIR: join(directory, "spool"),
        COLLECTOR_LOCAL_STORE_DIR: join(directory, "objects"),
        COLLECTOR_TOKEN: token,
        COLLECTOR_BIND_ADDRESS: `127.0.0.1:${port}`,
        COLLECTOR_ADMIN_ADDRESS: `127.0.0.1:${admin}`,
        COLLECTOR_MAX_BATCH_SECONDS: "1",
        COLLECTOR_DRAIN_SECONDS: "1",
        RUST_LOG: "error",
      },
      stdio: "ignore",
    },
  );
  const stop = async () => {
    if (process.exitCode !== null || process.signalCode !== null) return;
    const exited = once(process, "exit");
    process.kill("SIGTERM");
    await exited;
  };
  try {
    await waitFor(async () => {
      if (process.exitCode !== null)
        throw new Error("Collector exited before readiness.");
      return fetch(`http://127.0.0.1:${admin}/health/ready`)
        .then((response) => response.ok)
        .catch(() => false);
    });
  } catch (error) {
    await stop();
    throw error;
  }

  return { stop, port, admin };
};

const send = async (port: number, workspaceId: string, task: string) =>
  fetch(`http://127.0.0.1:${port}/v1/contents`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      schema: "gradiated.generation-content/1",
      generation_id: uuidv7(),
      workspace_id: workspaceId,
      task,
      trace_id: null,
      session_id: null,
      model: "test/model",
      provider: "gradiated",
      source: "hosted",
      trainable: true,
      started_at: new Date().toISOString(),
      completed_at: null,
      usage: null,
      retention_days: 30,
    }),
  });

it("registers tasks once at capture, preserving existing IDs and training settings", async () => {
  const member = await seedMember(db.database, { role: "admin" });
  await db.database
    .update(workspaces)
    .set({ defaultJudgeModel: "Qwen/Qwen3-0.6B" })
    .where(eq(workspaces.id, member.workspaceId));
  const directory = await mkdtemp(join(tmpdir(), "collector-tasks-"));
  let service = await start(directory, db.pool.options.connectionString!);
  try {
    for (const name of ["support-triage", "Billing Questions", ".", ".."])
      expect((await send(service.port, member.workspaceId, name)).status).toBe(
        202,
      );

    await waitFor(
      async () =>
        (
          await db.database
            .select()
            .from(tasks)
            .where(eq(tasks.workspaceId, member.workspaceId))
        ).length === 2,
    );
    const before = await db.database
      .select()
      .from(tasks)
      .where(eq(tasks.workspaceId, member.workspaceId));
    expect(before.map((task) => task.name).sort()).toEqual([
      "Billing Questions",
      "support-triage",
    ]);
    for (const task of before) {
      expect(task.trainingSchedule).toMatch(/^\d+ \d+ \* \* [0-6]$/);
      expect(task.judgeModelId).toBe("Qwen/Qwen3-0.6B");
    }
    await db.database
      .update(tasks)
      .set({ trainingSchedule: null, judgeModelId: "openai/gpt-5" })
      .where(eq(tasks.id, before[0]!.id));

    await db.database
      .update(workspaces)
      .set({ defaultJudgeModel: "openai/gpt-6-sol" })
      .where(eq(workspaces.id, member.workspaceId));
    for (let i = 0; i < 10; i++)
      expect(
        (await send(service.port, member.workspaceId, before[0]!.name)).status,
      ).toBe(202);
    const after = await db.database
      .select()
      .from(tasks)
      .where(eq(tasks.workspaceId, member.workspaceId));
    expect(after.map((task) => task.id).sort()).toEqual(
      before.map((task) => task.id).sort(),
    );
    expect(
      after.find((task) => task.id === before[0]!.id)?.trainingSchedule,
    ).toBeNull();
    const metrics = await fetch(
      `http://127.0.0.1:${service.admin}/metrics`,
    ).then((response) => response.text());
    expect(metrics).toContain("gradiated_collector_tasks_registered_total 2");

    await service.stop();
    service = await start(directory, db.pool.options.connectionString!);
    expect(
      (await send(service.port, member.workspaceId, before[0]!.name)).status,
    ).toBe(202);
    await waitFor(async () =>
      (
        await fetch(`http://127.0.0.1:${service.admin}/metrics`).then(
          (response) => response.text(),
        )
      ).includes("gradiated_collector_tasks_registered_total 1"),
    );
    const replayed = await db.database
      .select()
      .from(tasks)
      .where(eq(tasks.id, before[0]!.id));
    expect(replayed[0]).toMatchObject({
      name: before[0]!.name,
      trainingSchedule: null,
      judgeModelId: "openai/gpt-5",
    });
    expect(
      (await send(service.port, member.workspaceId, "new-default-task")).status,
    ).toBe(202);
    await waitFor(async () => {
      const rows = await db.database
        .select()
        .from(tasks)
        .where(eq(tasks.workspaceId, member.workspaceId));
      return rows.some(
        (task) =>
          task.name === "new-default-task" &&
          task.judgeModelId === "openai/gpt-6-sol",
      );
    });
  } finally {
    await service.stop();
    await rm(directory, { recursive: true, force: true });
  }
}, 30_000);

it("accepts and uploads during a PostgreSQL outage, then registers pending tasks after restart", async () => {
  const member = await seedMember(db.database, { role: "admin" });
  const directory = await mkdtemp(join(tmpdir(), "collector-outage-"));
  let service = await start(
    directory,
    "postgresql://test:test@127.0.0.1:1/test",
  );
  try {
    expect(
      (await send(service.port, member.workspaceId, "outage-task")).status,
    ).toBe(202);
    await waitFor(async () =>
      (await readdir(join(directory, "objects"), { recursive: true })).some(
        (name) => name.endsWith(".manifest.json"),
      ),
    );
    expect(
      await readdir(join(directory, "spool/task-registrations")),
    ).toHaveLength(1);
    await service.stop();

    service = await start(directory, db.pool.options.connectionString!);
    await waitFor(
      async () =>
        (
          await db.database
            .select()
            .from(tasks)
            .where(eq(tasks.workspaceId, member.workspaceId))
        ).length === 1,
    );
    await waitFor(
      async () =>
        (await readdir(join(directory, "spool/task-registrations"))).length ===
        0,
    );
    expect(
      (
        await db.database
          .select()
          .from(tasks)
          .where(eq(tasks.workspaceId, member.workspaceId))
      )[0]?.name,
    ).toBe("outage-task");
  } finally {
    await service.stop();
    await rm(directory, { recursive: true, force: true });
  }
}, 30_000);
