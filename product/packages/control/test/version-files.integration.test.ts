import { createVersionFileStore } from "../src/training/version-file-store.js";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { v7 as uuidv7 } from "uuid";
import { eq } from "drizzle-orm";
import {
  createTrainingArtifactCleanup,
  deleteArchivedTasks,
} from "../src/training/artifact-cleanup.js";
import {
  organizationMembers,
  taskVersions,
  taskVersionFiles,
  workspaces,
  tasks,
} from "../src/db/schema/index.js";
import { createVersionFiles } from "../src/training/version-files.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import { seedUser } from "./support/fixtures.js";
import { seedTrainingTask, trainingAdapter } from "./support/training.js";

const benchmark = JSON.stringify({
  schema_version: 1,
  comparison_model_id: null,
  workload: "Synthetic workload",
  notes: "",
  cost: null,
  speed: null,
  quality: null,
});

describe("version files", () => {
  let db: TestDatabase;
  beforeAll(async () => {
    db = await createTestDatabase();
  });
  afterAll(() => db.dispose());

  const setup = async () => {
    const member = await seedTrainingTask(db.database, "Qwen/Qwen3-0.6B");
    const [version] = await db.database
      .insert(taskVersions)
      .values({
        id: uuidv7(),
        workspaceId: member.workspaceId,
        taskId: member.task.id,
        trainingRunId: null,
        name: `${member.task.name}-v1`,
        baseModelId: member.input.baseModelId,
        status: "available",
        adapter: trainingAdapter,
      })
      .returning();
    const objects = new Map<string, Buffer>();
    const snapshots = new Map<string, Buffer>();
    const storage = {
      signUpload: vi.fn(
        async (key: string) => `https://storage.invalid/${key}`,
      ),
      signDownload: vi.fn(
        async (key: string) => `https://storage.invalid/${key}?download`,
      ),
      head: vi.fn(async (key: string) => {
        const bytes = objects.get(key);
        if (!bytes)
          throw Object.assign(new Error("Missing"), { name: "NotFound" });

        const versionId = uuidv7();
        snapshots.set(versionId, Buffer.from(bytes));
        return {
          sizeBytes: bytes.length,
          versionId,
          sha256: undefined,
        };
      }),
      read: async (
        key: string,
        options: { maxBytes: number; versionId?: string },
      ) => {
        const bytes = options.versionId
          ? snapshots.get(options.versionId)
          : objects.get(key);
        if (!bytes || bytes.length > options.maxBytes)
          throw new Error("Read failed");

        return bytes;
      },
      copy: vi.fn(
        async (_source: string, destination: string, versionId: string) => {
          objects.set(destination, Buffer.from(snapshots.get(versionId)!));
        },
      ),
      delete: vi.fn(async (keys: string[]) => {
        for (const key of keys) objects.delete(key);
      }),
    };
    const service = createVersionFiles(db.database, storage);
    const key = [member.workspaceId, member.task.name, version!.id] as const;
    const upload = async (name: string, content: string) => {
      const bytes = Buffer.from(content);
      const grant = await service.create(member.userId, ...key, {
        name,
        size_bytes: bytes.length,
        content_type: "text/markdown",
      });
      objects.set(new URL(grant.upload_url).pathname.slice(1), bytes);

      return service.complete(member.userId, ...key, grant.id);
    };

    return {
      member,
      version: version!,
      service,
      storage,
      key,
      upload,
      objects,
    };
  };

  it("batches named ready files within the workspace and requested versions", async () => {
    const first = await setup();
    const second = await setup();
    const named = await first.upload("benchmark.json", benchmark);
    await first.upload("report.md", "Report");
    await second.upload("benchmark.json", benchmark);
    const files = createVersionFileStore(db.database);
    expect(
      (
        await files.listReadyNamed(
          first.member.workspaceId,
          [first.version.id, second.version.id],
          "benchmark.json",
        )
      ).map((file) => file.id),
    ).toEqual([named.id]);
    expect(
      await files.listReadyNamed(
        first.member.workspaceId,
        [],
        "benchmark.json",
      ),
    ).toEqual([]);
    expect(
      await files.listReadyNamed(
        first.member.workspaceId,
        [second.version.id],
        "benchmark.json",
      ),
    ).toEqual([]);
  });

  it("publishes, lists, reads and downloads a report", async () => {
    const { member, service, key, upload } = await setup();
    const file = await upload("report.md", "# Training report");

    expect(file).toMatchObject({ name: "report.md", status: "ready" });
    expect(
      (await service.list(member.userId, ...key)).map((value) => value.name),
    ).toEqual(["report.md"]);
    expect(await service.content(member.userId, ...key, file.id)).toEqual({
      name: "report.md",
      content_type: "text/markdown",
      content: "# Training report",
    });
    expect(
      (await service.download(member.userId, ...key, file.id)).url,
    ).toContain(file.id);
  });

  it("finds a version and a ready file by name", async () => {
    const { member, version, service, upload } = await setup();
    await upload("report.md", "# Training report");
    const byName = [
      member.workspaceId,
      member.task.name,
      version.name,
    ] as const;

    expect(
      (await service.list(member.userId, ...byName)).map((file) => file.name),
    ).toEqual(["report.md"]);
    await expect(
      service.content(member.userId, ...byName, "report.md"),
    ).resolves.toMatchObject({ content: "# Training report" });
    await expect(
      service.content(member.userId, ...byName, "missing.md"),
    ).rejects.toMatchObject({ code: "not_found" });
    await expect(
      service.list(member.userId, member.workspaceId, member.task.name, "v9"),
    ).rejects.toMatchObject({ code: "not_found" });
  });

  it("replaces a file with the same name and deletes the old object", async () => {
    const { member, service, storage, key, upload } = await setup();
    const first = await upload("report.md", "# v1");
    const second = await upload("report.md", "# v2");

    const files = await service.list(member.userId, ...key);
    expect(files.map((value) => value.id)).toEqual([second.id]);
    expect(storage.delete).toHaveBeenCalledWith([
      expect.stringContaining(first.id),
      expect.stringContaining(first.id),
    ]);
    expect(
      (await service.content(member.userId, ...key, second.id)).content,
    ).toBe("# v2");
  });

  it("refuses a workload benchmark that does not match its schema", async () => {
    const { member, service, key, upload } = await setup();
    for (const content of ["{}", "not json", '{"schema_version":2}'])
      await expect(upload("benchmark.json", content)).rejects.toMatchObject({
        code: "conflict",
      });
    expect(await service.list(member.userId, ...key)).toEqual([]);
    await expect(upload("benchmark.json", benchmark)).resolves.toMatchObject({
      name: "benchmark.json",
      status: "ready",
    });
  });

  it("rejects a completion before the bytes arrive or with the wrong size", async () => {
    const { member, service, key, objects } = await setup();
    const grant = await service.create(member.userId, ...key, {
      name: "metrics.csv",
      size_bytes: 10,
      content_type: "text/csv",
    });

    await expect(
      service.complete(member.userId, ...key, grant.id),
    ).rejects.toMatchObject({ code: "conflict" });
    objects.set(
      new URL(grant.upload_url).pathname.slice(1),
      Buffer.from("short"),
    );
    await expect(
      service.complete(member.userId, ...key, grant.id),
    ).rejects.toMatchObject({ code: "conflict" });
    expect(await service.list(member.userId, ...key)).toEqual([]);
  });

  it("only lets workspace admins manage files and refuses binary content reads", async () => {
    const { member, service, key, upload } = await setup();
    const viewerId = await seedUser(db.database);
    await db.database.insert(organizationMembers).values({
      organizationId: member.organizationId,
      userId: viewerId,
      role: "member",
      status: "active",
    });
    const viewer = { userId: viewerId };
    const pdf = await upload("report.pdf", "%PDF");

    await expect(
      service.create(viewer.userId, ...key, {
        name: "notes.md",
        size_bytes: 4,
        content_type: "text/markdown",
      }),
    ).rejects.toMatchObject({ code: "forbidden" });
    await expect(
      service.content(viewer.userId, ...key, pdf.id),
    ).rejects.toMatchObject({ code: "conflict" });
    expect(
      (await service.list(viewer.userId, ...key)).map((value) => value.name),
    ).toEqual(["report.pdf"]);
  });

  it("deletes a file", async () => {
    const { member, service, key, upload } = await setup();
    const file = await upload("notes.md", "hello");

    await service.remove(member.userId, ...key, file.id);
    expect(await service.list(member.userId, ...key)).toEqual([]);
  });
  it("reads eval files above the usual inline limit", async () => {
    const { member, service, key, upload } = await setup();
    const large = "x".repeat(3 * 1024 * 1024);
    const evalFile = await upload("run.eval.json", large);
    const dataFile = await upload("rows.json", large);

    expect(
      (await service.content(member.userId, ...key, evalFile.id)).content,
    ).toHaveLength(large.length);
    await expect(
      service.content(member.userId, ...key, dataFile.id),
    ).rejects.toMatchObject({ code: "conflict" });
  });

  it("returns a controlled conflict for malformed UTF-8 text", async () => {
    const { member, service, key, upload, objects } = await setup();
    const file = await upload("report.md", "x");
    objects.set(
      `version-files/${file.versionId}/${file.id}`,
      Buffer.from([0xff]),
    );

    await expect(
      service.content(member.userId, ...key, file.id),
    ).rejects.toMatchObject({
      code: "conflict",
      message: expect.stringContaining("UTF-8"),
    });
  });

  it("retries deleted objects and protects archived versions until file cleanup", async () => {
    const { member, service, key, upload, objects, storage } = await setup();
    const old = await upload("report.md", "old");
    storage.delete.mockRejectedValueOnce(new Error("S3 outage"));
    const current = await upload("report.md", "new");
    expect(objects.has(`version-files/${old.versionId}/${old.id}`)).toBe(true);
    await db.database
      .update(workspaces)
      .set({ archivedAt: new Date() })
      .where(eq(workspaces.id, member.workspaceId));
    const engine = { updateSchedule: vi.fn() };
    await deleteArchivedTasks(db.database, engine);
    expect(
      await db.database
        .select()
        .from(tasks)
        .where(eq(tasks.id, member.task.id)),
    ).toHaveLength(1);

    const cleanup = createTrainingArtifactCleanup(
      db.database,
      {
        delete: storage.delete,
        list: async () => ({ keys: [], prefixes: [] }),
        read: async () => new Uint8Array(),
      },
      () => new Date(Date.now() + 4 * 60 * 60 * 1000),
    );
    storage.delete.mockRejectedValueOnce(new Error("S3 outage"));
    await expect(cleanup()).rejects.toThrow("S3 outage");
    expect(
      await db.database
        .select()
        .from(taskVersionFiles)
        .where(eq(taskVersionFiles.id, old.id)),
    ).toHaveLength(1);
    for (let pass = 0; pass < 30; pass++) await cleanup();
    expect(objects.has(`version-files/${old.versionId}/${old.id}`)).toBe(false);
    expect(
      objects.has(`version-files/${current.versionId}/${current.id}`),
    ).toBe(false);
    await deleteArchivedTasks(db.database, engine);
    expect(
      await db.database
        .select()
        .from(tasks)
        .where(eq(tasks.id, member.task.id)),
    ).toHaveLength(0);
  });

  it("cleans abandoned uploads only after their grants have expired", async () => {
    const { member, service, key, objects, storage } = await setup();
    const grant = await service.create(member.userId, ...key, {
      name: "notes.md",
      size_bytes: 1,
      content_type: "text/markdown",
    });
    const objectKey = new URL(grant.upload_url).pathname.slice(1);
    objects.set(objectKey, Buffer.from("x"));
    const store = {
      delete: storage.delete,
      list: async () => ({ keys: [], prefixes: [] }),
      read: async () => new Uint8Array(),
    };
    await createTrainingArtifactCleanup(db.database, store)();
    expect(objects.has(objectKey)).toBe(true);
    const cleanup = createTrainingArtifactCleanup(
      db.database,
      store,
      () => new Date(Date.now() + 4 * 60 * 60 * 1000),
    );
    for (let pass = 0; pass < 30; pass++) await cleanup();
    expect(objects.has(objectKey)).toBe(false);
  });
  it("publishes a stable copy and ignores subsequent writes through the upload grant", async () => {
    const { member, service, key, objects } = await setup();
    const grant = await service.create(member.userId, ...key, {
      name: "report.md",
      size_bytes: 3,
      content_type: "text/markdown",
    });
    const staging = new URL(grant.upload_url).pathname.slice(1);
    objects.set(staging, Buffer.from("old"));
    const file = await service.complete(member.userId, ...key, grant.id);
    objects.set(staging, Buffer.from("new"));
    await service.complete(member.userId, ...key, grant.id);

    expect(
      (await service.content(member.userId, ...key, file.id)).content,
    ).toBe("old");
  });

  it("serializes concurrent publications and makes repeated completion idempotent", async () => {
    const { member, service, key, objects, storage } = await setup();
    const grants = await Promise.all(
      ["one", "two"].map(async (content) => {
        const grant = await service.create(member.userId, ...key, {
          name: "report.md",
          size_bytes: 3,
          content_type: "text/markdown",
        });
        objects.set(
          new URL(grant.upload_url).pathname.slice(1),
          Buffer.from(content),
        );
        return grant;
      }),
    );
    const results = await Promise.all(
      grants.map((grant) => service.complete(member.userId, ...key, grant.id)),
    );
    const ready = await service.list(member.userId, ...key);
    expect(ready).toHaveLength(1);
    const stale = results.find((file) => file.id !== ready[0]!.id)!;
    await expect(
      service.complete(member.userId, ...key, stale.id),
    ).rejects.toMatchObject({ code: "not_found" });
    const copyCount = storage.copy.mock.calls.length;
    await Promise.all([
      service.complete(member.userId, ...key, ready[0]!.id),
      service.complete(member.userId, ...key, ready[0]!.id),
    ]);
    expect(storage.copy.mock.calls).toHaveLength(copyCount);
  });

  it("rejects expired grants and reports storage outages without claiming an upload is missing", async () => {
    const { member, service, key, storage } = await setup();
    const grant = await service.create(member.userId, ...key, {
      name: "report.md",
      size_bytes: 3,
      content_type: "text/markdown",
    });
    storage.head.mockRejectedValueOnce(new Error("Access denied"));
    await expect(
      service.complete(member.userId, ...key, grant.id),
    ).rejects.toMatchObject({ code: "unavailable" });
    await db.database
      .update(taskVersionFiles)
      .set({ createdAt: new Date(Date.now() - 2 * 60 * 60 * 1000) })
      .where(eq(taskVersionFiles.id, grant.id));
    await expect(
      service.complete(member.userId, ...key, grant.id),
    ).rejects.toMatchObject({
      code: "conflict",
      message: expect.stringContaining("expired"),
    });
  });

  it("never revives a removed upload", async () => {
    const { member, service, key, objects } = await setup();
    const grant = await service.create(member.userId, ...key, {
      name: "report.md",
      size_bytes: 3,
      content_type: "text/markdown",
    });
    objects.set(
      new URL(grant.upload_url).pathname.slice(1),
      Buffer.from("new"),
    );
    await service.remove(member.userId, ...key, grant.id);

    await expect(
      service.complete(member.userId, ...key, grant.id),
    ).rejects.toMatchObject({ code: "not_found" });
    expect(await service.list(member.userId, ...key)).toEqual([]);
  });
  it("keeps deletion ordered after an in-flight publication", async () => {
    const { member, service, key, objects, storage } = await setup();
    const grant = await service.create(member.userId, ...key, {
      name: "report.md",
      size_bytes: 3,
      content_type: "text/markdown",
    });
    objects.set(
      new URL(grant.upload_url).pathname.slice(1),
      Buffer.from("new"),
    );
    let copying!: () => void;
    let release!: () => void;
    const started = new Promise<void>((resolve) => {
      copying = resolve;
    });
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const copy = storage.copy.getMockImplementation()!;
    storage.copy.mockImplementationOnce(async (...args) => {
      copying();
      await gate;
      await copy(...args);
    });
    const publication = service.complete(member.userId, ...key, grant.id);
    await started;
    const deletion = service.remove(member.userId, ...key, grant.id);
    release();
    await Promise.all([publication, deletion]);

    expect(await service.list(member.userId, ...key)).toEqual([]);
    expect(objects.has(`version-files/${key[2]}/${grant.id}`)).toBe(false);
    await expect(
      service.complete(member.userId, ...key, grant.id),
    ).rejects.toMatchObject({ code: "not_found" });
  });

  it("rejects reads across workspace, version and file boundaries", async () => {
    const own = await setup();
    const other = await setup();
    const file = await own.upload("report.md", "private");
    const foreign = await other.upload("report.md", "other");

    await expect(
      own.service.content(other.member.userId, ...own.key, file.id),
    ).rejects.toMatchObject({ code: "not_found" });
    await expect(
      own.service.content(
        own.member.userId,
        own.key[0],
        own.key[1],
        other.version.id,
        foreign.id,
      ),
    ).rejects.toMatchObject({ code: "not_found" });
    await expect(
      own.service.content(own.member.userId, ...own.key, foreign.id),
    ).rejects.toMatchObject({ code: "not_found" });
  });
});
