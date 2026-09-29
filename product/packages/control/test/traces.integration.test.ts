import { randomUUID } from "node:crypto";
import * as zlib from "node:zlib";
import { v7 } from "uuid";
import { eq } from "drizzle-orm";
import {
  afterAll,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { createWorkspaceApiKeyService } from "../src/workspaces/service.js";
import { createTraceService } from "../src/traces/service.js";
import { traceTaskKey } from "../src/traces/content.js";
import { createTraceCleanup } from "../src/traces/cleanup.js";
import type { ContentStore } from "../src/traces/storage.js";
import { workspaces } from "../src/db/schema/index.js";
import { createMemoryContentStore } from "./support/content-store.js";
import { seedMember } from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

const compress = (
  zlib as unknown as { zstdCompressSync: (input: Buffer) => Buffer }
).zstdCompressSync;
describe("generation content", () => {
  let db: TestDatabase;
  let objects: Map<string, Buffer>;
  let store: ContentStore;
  beforeAll(async () => {
    db = await createTestDatabase();
  });
  afterAll(() => db.dispose());
  beforeEach(() => {
    objects = new Map();
    store = createMemoryContentStore(objects);
  });
  const fixture = async (role: "owner" | "member" = "owner", daysAgo = 0) => {
    const scope = await seedMember(db.database, { role });
    const started = new Date(Date.now() - daysAgo * 86_400_000);
    const generation = v7({ msecs: started.getTime() });
    const record = {
      generation_id: generation,
      workspace_id: scope.workspaceId,
      task: "test",
      trace_id: "trace-one",
      model: "model",
      source: "relay",
      trainable: false,
      started_at: started.toISOString(),
      completed_at: started.toISOString(),
      usage: { input: 5, output: 2 },
      retention_days: 90,
      raw: { request: { model: "model" }, response: { text: "synthetic" } },
      canonical: null,
    };
    const frame = compress(Buffer.from(JSON.stringify(record) + "\n"));
    const key = `v1/ws=${scope.workspaceId}/task=test/dt=${started.toISOString().slice(0, 10)}/hr=${started.toISOString().slice(11, 13)}/replica-batch.manifest.json`;
    const row = {
      ...record,
      raw: undefined,
      canonical: undefined,
      offset: 0,
      length: frame.length,
    };
    objects.set(
      key,
      Buffer.from(
        JSON.stringify({
          schema: "gradiated.generation-content-manifest/1",
          generations: [row, row],
        }),
      ),
    );
    objects.set(key.replace(".manifest.json", ".jsonl.zst"), frame);
    return {
      ...scope,
      key,
      generation,
      record,
      workspaceService: createWorkspaceApiKeyService(db.database),
      service: createTraceService(db.database, store),
    };
  };
  it("lists deduplicated metadata and fetches a single compressed generation frame", async () => {
    const f = await fixture();
    const page = await f.service.list(f.userId, f.workspaceId, {
      task: "test",
    });
    expect(page.data).toHaveLength(1);
    expect(page.data[0]).not.toHaveProperty("raw");
    const content = await f.service.content(
      f.userId,
      f.workspaceId,
      f.generation,
      page.data[0]!.content_ref,
    );
    expect(content.raw).toEqual(f.record.raw);
    expect(store.read).toHaveBeenLastCalledWith(
      f.key.replace(".manifest.json", ".jsonl.zst"),
      expect.objectContaining({ offset: 0 }),
    );
  });
  it.each([0, 1])(
    "handles a record %i bytes above the collector limit",
    async (extra) => {
      const f = await fixture();
      const limit = 32 * 1024 * 1024;
      const empty = { ...f.record, raw: { text: "" } };
      const text = "x".repeat(
        limit - Buffer.byteLength(JSON.stringify(empty)) + extra,
      );
      const record = Buffer.from(JSON.stringify({ ...empty, raw: { text } }));
      expect(record.length).toBe(limit + extra);
      const frame = compress(Buffer.concat([record, Buffer.from("\n")]));
      const manifest = JSON.parse(objects.get(f.key)!.toString());
      manifest.generations.forEach((row: { length: number }) => {
        row.length = frame.length;
      });
      objects.set(f.key, Buffer.from(JSON.stringify(manifest)));
      objects.set(f.key.replace(".manifest.json", ".jsonl.zst"), frame);

      const result = f.service.content(
        f.userId,
        f.workspaceId,
        f.generation,
        Buffer.from(JSON.stringify(f.key)).toString("base64url"),
      );
      if (extra === 0) {
        expect((await result).raw?.text).toBe(text);
      } else {
        await expect(result).rejects.toMatchObject({ code: "unavailable" });
      }
    },
  );
  it("requires membership before touching S3 and rejects cross-workspace references", async () => {
    const f = await fixture();
    const other = await fixture();
    await expect(
      f.service.list(other.userId, f.workspaceId, {
        task: "test",
      }),
    ).rejects.toMatchObject({ code: "not_found" });
    expect(store.list).not.toHaveBeenCalled();
    await expect(
      f.service.content(
        f.userId,
        f.workspaceId,
        other.generation,
        Buffer.from(JSON.stringify(other.key)).toString("base64url"),
      ),
    ).rejects.toMatchObject({ code: "not_found" });
    expect(store.read).not.toHaveBeenCalled();
  });
  it("does not allow a member to enable capture or delete the workspace", async () => {
    const f = await fixture("member");
    await expect(
      f.workspaceService.updateWorkspace(f.userId, f.workspaceId, {
        trace_capture_enabled: true,
        trace_retention_days: 90,
      }),
    ).rejects.toMatchObject({ code: "forbidden" });
    await expect(
      f.workspaceService.archiveWorkspace(f.userId, f.workspaceId),
    ).rejects.toMatchObject({ code: "forbidden" });
  });
  it("persists capture settings without changing training eligibility", async () => {
    const f = await fixture();
    await f.workspaceService.updateWorkspace(f.userId, f.workspaceId, {
      trace_capture_enabled: true,
      trace_retention_days: 180,
    });
    const [row] = await db.database
      .select()
      .from(workspaces)
      .where(eq(workspaces.id, f.workspaceId));
    expect(row).toMatchObject({
      traceCaptureEnabled: true,
      traceRetentionDays: 180,
    });
    expect(
      (
        await f.service.list(f.userId, f.workspaceId, {
          task: "test",
        })
      ).data[0]?.trainable,
    ).toBe(false);
  });
  it("patches only the supplied workspace fields", async () => {
    const f = await fixture();
    await f.workspaceService.updateWorkspace(f.userId, f.workspaceId, {
      trace_capture_enabled: true,
    });
    const workspace = await f.workspaceService.updateWorkspace(
      f.userId,
      f.workspaceId,
      { trace_retention_days: 180 },
    );
    expect(workspace).toMatchObject({
      traceCaptureEnabled: true,
      traceRetentionDays: 180,
    });
  });
  it("denies expired content using its recorded retention", async () => {
    const f = await fixture("owner", 100);
    await expect(
      f.service.content(
        f.userId,
        f.workspaceId,
        f.generation,
        Buffer.from(JSON.stringify(f.key)).toString("base64url"),
      ),
    ).rejects.toMatchObject({ code: "not_found" });
    await createTraceCleanup(db.database, store)();
    expect(objects.size).toBe(2);
    expect(store.delete).not.toHaveBeenCalled();
  });
  it("blocks archived workspace reads and deletes late-arriving content on the next pass", async () => {
    const f = await fixture();
    await f.workspaceService.archiveWorkspace(f.userId, f.workspaceId);
    await expect(
      f.service.list(f.userId, f.workspaceId, {
        task: "test",
      }),
    ).rejects.toMatchObject({ code: "not_found" });
    const cleanup = createTraceCleanup(db.database, store);
    await cleanup();
    expect(objects.size).toBe(0);
    objects.set(f.key, Buffer.from("late flush"));
    await cleanup();
    expect(objects.size).toBe(0);
  });
  it("retries deletion failures and cleans orphaned prefixes", async () => {
    const orphan = `v1/ws=${randomUUID()}/task=test/dt=2026-01-01/hr=00/batch.jsonl.zst`;
    objects.set(orphan, Buffer.from("synthetic"));
    vi.mocked(store.delete).mockRejectedValueOnce(new Error("S3 outage"));
    const cleanup = createTraceCleanup(db.database, store);
    await expect(cleanup()).rejects.toThrow("S3 outage");
    expect(objects.size).toBe(1);
    await cleanup();
    expect(objects.size).toBe(0);
  });
  it("rejects malformed cursors and reports corrupt manifests", async () => {
    const f = await fixture();
    await expect(
      f.service.list(f.userId, f.workspaceId, {
        task: "test",
        cursor: "garbage",
      }),
    ).rejects.toMatchObject({ code: "not_found" });
    objects.set(f.key, Buffer.from("broken"));
    await expect(
      f.service.list(f.userId, f.workspaceId, {
        task: "test",
      }),
    ).rejects.toMatchObject({ code: "unavailable" });
  });
  it("retention changes leave existing captures readable until their recorded expiry", async () => {
    const f = await fixture("owner", 40);
    for (const days of [30, 180, 30] as const) {
      await f.workspaceService.updateWorkspace(f.userId, f.workspaceId, {
        trace_capture_enabled: true,
        trace_retention_days: days,
      });
      await expect(
        f.service.content(
          f.userId,
          f.workspaceId,
          f.generation,
          Buffer.from(JSON.stringify(f.key)).toString("base64url"),
        ),
      ).resolves.toMatchObject({ raw: f.record.raw });
    }
    await createTraceCleanup(db.database, store)();
    expect(objects.size).toBe(2);
    expect(store.delete).not.toHaveBeenCalled();
  });
  it("paginates large manifests without fetching content or losing rows", async () => {
    const f = await fixture();
    const manifest = JSON.parse(objects.get(f.key)!.toString());
    manifest.generations = Array.from({ length: 205 }, () => ({
      ...manifest.generations[0],
      generation_id: v7(),
    }));
    objects.set(f.key, Buffer.from(JSON.stringify(manifest)));
    let cursor: string | undefined;
    const ids = new Set<string>();
    for (let index = 0; index < 3; index++) {
      const page = await f.service.list(f.userId, f.workspaceId, {
        task: "test",
        ...(cursor ? { cursor } : {}),
      });
      expect(page.data.length).toBeLessThanOrEqual(100);
      page.data.forEach((row) => ids.add(row.generation_id));
      cursor = page.next_cursor ?? undefined;
    }
    expect(ids.size).toBe(205);
    expect(
      vi
        .mocked(store.read)
        .mock.calls.every(([key]) => key.endsWith(".manifest.json")),
    ).toBe(true);
  });
  it("rejects a cursor that points to another workspace's manifest", async () => {
    const f = await fixture();
    const other = await fixture();
    const cursor = Buffer.from(
      JSON.stringify({
        hour: Math.floor(Date.now() / 3_600_000) * 3_600_000,
        task: "test",
        manifests: [other.key],
        offset: 0,
      }),
    ).toString("base64url");
    await expect(
      f.service.list(f.userId, f.workspaceId, {
        task: "test",
        cursor,
      }),
    ).rejects.toMatchObject({ code: "not_found" });
    expect(store.read).not.toHaveBeenCalled();
  });
  it("skips empty hours within a bounded scan", async () => {
    const f = await fixture("owner", 0.5);
    const page = await f.service.list(f.userId, f.workspaceId, {
      task: "test",
    });
    expect(page.data).toHaveLength(1);
    expect(vi.mocked(store.list).mock.calls.length).toBeGreaterThan(1);
    expect(vi.mocked(store.list).mock.calls.length).toBeLessThanOrEqual(24);
  });
  it("lists older captures after workspace retention is shortened", async () => {
    const f = await fixture("owner", 40);
    await f.workspaceService.updateWorkspace(f.userId, f.workspaceId, {
      trace_capture_enabled: true,
      trace_retention_days: 30,
    });
    const cursor = Buffer.from(
      JSON.stringify({
        hour:
          Math.floor((Date.now() - 40 * 86_400_000) / 3_600_000) * 3_600_000,
        task: "test",
      }),
    ).toString("base64url");
    const page = await f.service.list(f.userId, f.workspaceId, {
      task: "test",
      cursor,
    });
    expect(page.data).toHaveLength(1);
    expect(page.data[0]?.generation_id).toBe(f.generation);
  });
  it("hashes non-path-safe task headers exactly as the collector", () => {
    expect(traceTaskKey("support-triage")).toBe("support-triage");
    expect(traceTaskKey("../other/task")).toMatch(/^h-[a-f0-9]{32}$/);
  });
});
