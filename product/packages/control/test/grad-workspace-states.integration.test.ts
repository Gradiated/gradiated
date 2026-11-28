import { eq, sql } from "drizzle-orm";
import {
  afterAll,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  gradWorkspaceStateOutbox as outbox,
  organizations,
  workspaces,
} from "../src/db/schema/index.js";
import {
  createGradWorkspaceStateSync,
  startGradWorkspaceStateSweep,
} from "../src/training/grad-workspace-states.js";
import { createWorkspaceApiKeyService } from "../src/workspaces/service.js";
import { seedMember, seedWorkspace } from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

const GRAD_URL = "http://grad-internal.test:8789";

type Call = { url: string; method: string; body: unknown; auth: string };

const problem = (status: number, code: string) =>
  new Response(JSON.stringify({ status, code }), {
    status,
    headers: { "content-type": "application/problem+json" },
  });

describe("grad workspace states", () => {
  let testDatabase: TestDatabase;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
  });

  afterAll(() => testDatabase.dispose());

  beforeEach(async () => {
    await testDatabase.database.delete(outbox);
  });

  const rows = () =>
    testDatabase.database.select().from(outbox).orderBy(outbox.createdAt);
  const rowOf = async (workspaceId: string) =>
    (
      await testDatabase.database
        .select()
        .from(outbox)
        .where(eq(outbox.workspaceId, workspaceId))
    )[0];
  const setOrganizationStatus = (
    organizationId: string,
    status: "active" | "suspended",
  ) =>
    testDatabase.database
      .update(organizations)
      .set({ status })
      .where(eq(organizations.id, organizationId));
  const makeDue = () =>
    testDatabase.database.update(outbox).set({ nextAttemptAt: sql`now()` });

  const grad = (respond: (call: Call) => Promise<Response> | Response) => {
    const calls: Call[] = [];
    const authorization = vi.fn(
      async (call: { workspaceId: string; scopes: readonly string[] }) =>
        `jwt-for-${call.workspaceId}-${call.scopes.join(",")}`,
    );
    const log = vi.fn();
    const fetch = vi.fn(
      async (input: string | URL | Request, init?: RequestInit) => {
        const call = {
          url: String(input),
          method: init?.method ?? "GET",
          body: JSON.parse(String(init?.body)),
          auth: new Headers(init?.headers).get("authorization") ?? "",
        };
        calls.push(call);

        return respond(call);
      },
    );
    const sync = createGradWorkspaceStateSync({
      database: testDatabase.database,
      baseUrl: GRAD_URL,
      authorization,
      log,
      fetch,
    });

    return { calls, authorization, log, fetch, sync };
  };

  it("queues the state in the transaction that archives the workspace", async () => {
    const { userId, workspaceId } = await seedMember(testDatabase.database, {
      role: "admin",
    });

    await testDatabase.database
      .transaction(async (tx) => {
        await tx
          .update(workspaces)
          .set({ archivedAt: new Date() })
          .where(eq(workspaces.id, workspaceId));
        expect(
          await tx
            .select()
            .from(outbox)
            .where(eq(outbox.workspaceId, workspaceId)),
        ).toMatchObject([{ state: "suspended" }]);
        tx.rollback();
      })
      .catch(() => undefined);
    expect(await rowOf(workspaceId)).toBeUndefined();

    await createWorkspaceApiKeyService(testDatabase.database).archiveWorkspace(
      userId,
      workspaceId,
    );
    expect(await rowOf(workspaceId)).toMatchObject({
      state: "suspended",
      generation: 1,
      attempts: 0,
    });
  });

  it("suspends and reinstates an organization's unarchived workspaces, keeping only the newest state", async () => {
    const { organizationId, workspaceId } = await seedMember(
      testDatabase.database,
      { role: "admin" },
    );
    const archived = await seedWorkspace(testDatabase.database, {
      organizationId,
      archived: true,
    });

    await setOrganizationStatus(organizationId, "suspended");
    expect(await rows()).toMatchObject([
      { workspaceId, state: "suspended", generation: 1 },
    ]);

    await setOrganizationStatus(organizationId, "active");
    expect(await rows()).toMatchObject([
      { workspaceId, state: "active", generation: 2 },
    ]);
    expect(await rowOf(archived)).toBeUndefined();

    // Unarchiving in a suspended organization keeps the workspace suspended.
    await setOrganizationStatus(organizationId, "suspended");
    await testDatabase.database
      .update(workspaces)
      .set({ archivedAt: null })
      .where(eq(workspaces.id, archived));
    expect(await rowOf(archived)).toMatchObject({ state: "suspended" });

    await setOrganizationStatus(organizationId, "active");
    expect(await rowOf(archived)).toMatchObject({ state: "active" });
  });

  it("queues deleted for the workspaces of a deleted organization, and nothing replaces it", async () => {
    const { organizationId, workspaceId } = await seedMember(
      testDatabase.database,
      { role: "admin" },
    );
    await setOrganizationStatus(organizationId, "suspended");

    await testDatabase.database
      .delete(organizations)
      .where(eq(organizations.id, organizationId));
    await testDatabase.database.execute(
      sql`select queue_grad_workspace_state(${workspaceId}::uuid, 'active')`,
    );

    expect(await rowOf(workspaceId)).toMatchObject({ state: "deleted" });
  });

  it("sends the newest state with a workspace-scoped service token and clears the row", async () => {
    const { organizationId, workspaceId } = await seedMember(
      testDatabase.database,
      { role: "admin" },
    );
    await setOrganizationStatus(organizationId, "suspended");
    await setOrganizationStatus(organizationId, "active");
    const { calls, authorization, sync } = grad(
      () =>
        new Response(JSON.stringify({ workspace_id: workspaceId }), {
          status: 200,
        }),
    );

    expect(await sync.sweep()).toEqual({ sent: 1, failed: 0 });

    expect(authorization).toHaveBeenCalledWith({
      workspaceId,
      scopes: ["workspaces:admin"],
    });
    expect(calls).toEqual([
      {
        url: `${GRAD_URL}/internal/v1/workspaces/${workspaceId}/state`,
        method: "PUT",
        body: { state: "active" },
        auth: `Bearer jwt-for-${workspaceId}-workspaces:admin`,
      },
    ]);
    expect(await rows()).toEqual([]);
  });

  it.each([
    ["a 5xx", () => problem(503, "unavailable"), "http 503 unavailable"],
    [
      "a network error",
      () => Promise.reject(new TypeError("fetch failed")),
      "request failed: TypeError",
    ],
  ])("retries after %s with backoff", async (_name, respond, lastError) => {
    const { userId, workspaceId } = await seedMember(testDatabase.database, {
      role: "admin",
    });
    await createWorkspaceApiKeyService(testDatabase.database).archiveWorkspace(
      userId,
      workspaceId,
    );
    const failing = grad(respond);

    expect(await failing.sync.sweep()).toEqual({ sent: 0, failed: 1 });
    expect(await failing.sync.sweep()).toEqual({ sent: 0, failed: 0 });
    const row = await rowOf(workspaceId);
    expect(row).toMatchObject({ state: "suspended", attempts: 1, lastError });
    expect(row!.nextAttemptAt.getTime()).toBeGreaterThan(Date.now() + 30_000);
    expect(failing.log).toHaveBeenCalledWith(
      "warn",
      "grad_workspace_state_failed",
      {
        workspace_id: workspaceId,
        reason: lastError,
        attempt: 1,
      },
    );

    await makeDue();
    const healthy = grad(() => new Response("{}", { status: 200 }));
    expect(await healthy.sync.sweep()).toEqual({ sent: 1, failed: 0 });
    expect(healthy.calls).toMatchObject([{ body: { state: "suspended" } }]);
    expect(await rows()).toEqual([]);
  });

  it("finishes a state that grad refuses because the workspace was deleted", async () => {
    const { organizationId, workspaceId } = await seedMember(
      testDatabase.database,
      { role: "admin" },
    );
    await setOrganizationStatus(organizationId, "suspended");
    const { log, sync } = grad(() => problem(409, "workspace_deleted"));

    expect(await sync.sweep()).toEqual({ sent: 1, failed: 0 });

    expect(await rows()).toEqual([]);
    expect(log).toHaveBeenCalledWith("warn", "grad_workspace_already_deleted", {
      workspace_id: workspaceId,
      reason: "suspended",
    });
  });

  it("keeps retrying other refusals", async () => {
    const { organizationId, workspaceId } = await seedMember(
      testDatabase.database,
      { role: "admin" },
    );
    await setOrganizationStatus(organizationId, "suspended");
    const { sync } = grad(() => problem(403, "insufficient_scope"));

    expect(await sync.sweep()).toEqual({ sent: 0, failed: 1 });
    expect(await rowOf(workspaceId)).toMatchObject({
      attempts: 1,
      lastError: "http 403 insufficient_scope",
    });
  });

  it("sends a state that changed while the previous one was in flight", async () => {
    const { organizationId, workspaceId } = await seedMember(
      testDatabase.database,
      { role: "admin" },
    );
    await setOrganizationStatus(organizationId, "suspended");
    const { calls, sync } = grad(async ({ body }) => {
      if ((body as { state: string }).state === "suspended")
        await setOrganizationStatus(organizationId, "active");

      return new Response("{}", { status: 200 });
    });

    expect(await sync.sweep()).toEqual({ sent: 2, failed: 0 });

    expect(calls.map((call) => call.body)).toEqual([
      { state: "suspended" },
      { state: "active" },
    ]);
    expect(await rows()).toEqual([]);
  });

  it("never sends a workspace twice from concurrent sweeps", async () => {
    const seeded = await Promise.all(
      [0, 1].map(() => seedMember(testDatabase.database, { role: "admin" })),
    );
    for (const { organizationId } of seeded)
      await setOrganizationStatus(organizationId, "suspended");
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const { calls, sync } = grad(async () => {
      if (calls.length === 1) await gate;

      return new Response("{}", { status: 200 });
    });

    const first = sync.sweep();
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    // The first sweep's workspace is in flight: another sweep sends only the other one.
    expect(await sync.sweep()).toEqual({ sent: 1, failed: 0 });
    release();
    expect(await first).toEqual({ sent: 1, failed: 0 });

    expect(calls.map((call) => call.url).sort()).toEqual(
      seeded
        .map(
          ({ workspaceId }) =>
            `${GRAD_URL}/internal/v1/workspaces/${workspaceId}/state`,
        )
        .sort(),
    );
    expect(await rows()).toEqual([]);
  });

  it("sends nothing without a grad URL, and the state change still succeeds", async () => {
    const { userId, workspaceId } = await seedMember(testDatabase.database, {
      role: "admin",
    });
    const fetch = vi.fn();
    const authorization = vi.fn();

    const stop = startGradWorkspaceStateSweep({
      database: testDatabase.database,
      baseUrl: undefined,
      authorization,
      log: vi.fn(),
      fetch,
      intervalMs: 10,
    });
    await createWorkspaceApiKeyService(testDatabase.database).archiveWorkspace(
      userId,
      workspaceId,
    );
    await new Promise((resolve) => setTimeout(resolve, 100));
    stop();

    expect(fetch).not.toHaveBeenCalled();
    expect(authorization).not.toHaveBeenCalled();
    expect(await rowOf(workspaceId)).toMatchObject({ state: "suspended" });
  });

  it("sweeps on an interval once grad is configured", async () => {
    const { organizationId } = await seedMember(testDatabase.database, {
      role: "admin",
    });
    await setOrganizationStatus(organizationId, "suspended");
    const fetch = vi.fn(async () => new Response("{}", { status: 200 }));

    const stop = startGradWorkspaceStateSweep({
      database: testDatabase.database,
      baseUrl: GRAD_URL,
      authorization: async () => "jwt",
      log: vi.fn(),
      fetch,
      intervalMs: 10,
    });
    await vi.waitFor(async () => expect(await rows()).toEqual([]));
    stop();

    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
