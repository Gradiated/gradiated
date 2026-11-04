import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { v7 as uuidv7 } from "uuid";
import { organizationMembers, taskVersions } from "../src/db/schema/index.js";
import { createVersionFiles } from "../src/training/version-files.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import { seedUser } from "./support/fixtures.js";
import { seedTrainingTask, trainingAdapter } from "./support/training.js";

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

        return {
          sizeBytes: bytes.length,
          versionId: undefined,
          sha256: undefined,
        };
      }),
      read: async (key: string, options: { maxBytes: number }) => {
        const bytes = objects.get(key);
        if (!bytes || bytes.length > options.maxBytes)
          throw new Error("Read failed");

        return bytes;
      },
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

  it("replaces a file with the same name and deletes the old object", async () => {
    const { member, service, storage, key, upload } = await setup();
    const first = await upload("report.md", "# v1");
    const second = await upload("report.md", "# v2");

    const files = await service.list(member.userId, ...key);
    expect(files.map((value) => value.id)).toEqual([second.id]);
    expect(storage.delete).toHaveBeenCalledWith([
      expect.stringContaining(first.id),
    ]);
    expect(
      (await service.content(member.userId, ...key, second.id)).content,
    ).toBe("# v2");
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
});
