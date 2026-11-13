import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { v7 as uuidv7 } from "uuid";
import { eq } from "drizzle-orm";
import {
  organizationMembers,
  taskVersions,
  workspaces,
} from "../src/db/schema/index.js";
import { createReportShares } from "../src/training/report-shares.js";
import { createVersionFiles } from "../src/training/version-files.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import { seedUser } from "./support/fixtures.js";
import { seedTrainingTask, trainingAdapter } from "./support/training.js";

describe("report shares", () => {
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
      signUpload: async (key: string) => `https://storage.invalid/${key}`,
      signDownload: vi.fn(
        async (key: string) => `https://storage.invalid/${key}?download`,
      ),
      head: async (key: string) => {
        const bytes = objects.get(key)!;
        const versionId = uuidv7();
        snapshots.set(versionId, Buffer.from(bytes));
        return { sizeBytes: bytes.length, versionId, sha256: undefined };
      },
      read: async (
        key: string,
        options: { maxBytes: number; versionId?: string },
      ) =>
        (options.versionId
          ? snapshots.get(options.versionId)
          : objects.get(key))!,
      copy: async (_source: string, destination: string, versionId: string) => {
        objects.set(destination, Buffer.from(snapshots.get(versionId)!));
      },
      delete: async (keys: string[]) => {
        for (const key of keys) objects.delete(key);
      },
    };
    const files = createVersionFiles(db.database, storage);
    const shares = createReportShares(db.database, storage, "test-secret");
    const key = [member.workspaceId, member.task.name, version!.id] as const;
    const upload = async (name: string, content: string) => {
      const bytes = Buffer.from(content);
      const grant = await files.create(member.userId, ...key, {
        name,
        size_bytes: bytes.length,
        content_type: "text/plain",
      });
      objects.set(new URL(grant.upload_url).pathname.slice(1), bytes);

      return files.complete(member.userId, ...key, grant.id);
    };

    return { member, version: version!, shares, storage, key, upload };
  };

  it("signs a stable link per version and serves only the report's files", async () => {
    const { member, version, shares, storage, key, upload } = await setup();
    const report = await upload(
      "report.md",
      '# Results\n\n{% chart type="line" data="loss.csv" x="step" y="loss" /%}\n\nSee validation-loss.csv.',
    );
    const data = await upload("loss.csv", "step,loss\n1,0.5\n");
    const hidden = await upload("internal-notes.txt", "private");
    await upload("validation-loss.csv", "step,loss\n1,0.6\n");
    await upload("on-loss.csv", "private");

    const link = await shares.get(member.userId, ...key);
    expect(link.versionId).toBe(version.id);
    expect(link.signature).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(await shares.get(member.userId, ...key)).toEqual(link);
    const { signature } = link;

    const shared = await shares.shared(version.id, signature);
    expect(shared).toMatchObject({
      task: member.task.name,
      version: version.name,
      baseModelId: member.input.baseModelId,
    });
    expect(shared.files.map((file) => file.name).sort()).toEqual([
      "loss.csv",
      "report.md",
      "validation-loss.csv",
    ]);
    expect(
      (await shares.sharedContent(version.id, signature, data.id)).content,
    ).toContain("0.5");
    expect(
      (await shares.sharedContent(version.id, signature, report.id)).content,
    ).toContain("# Results");
    await expect(
      shares.sharedContent(version.id, signature, hidden.id),
    ).rejects.toMatchObject({ code: "not_found" });
    await expect(
      shares.sharedDownload(version.id, signature, hidden.id),
    ).rejects.toMatchObject({ code: "not_found" });
    expect(storage.signDownload).not.toHaveBeenCalled();
  });

  it("refuses wrong signatures, other keys and archived workspaces", async () => {
    const { member, version, shares, key, upload } = await setup();
    await upload("report.md", "# Report");
    const { signature } = await shares.get(member.userId, ...key);
    const flipped = `${signature[0] === "A" ? "B" : "A"}${signature.slice(1)}`;
    const otherKey = createReportShares(db.database, undefined, "other-secret");

    for (const attempt of [
      shares.shared(version.id, flipped),
      shares.shared(version.id, "short"),
      shares.shared("not-a-uuid", signature),
      shares.shared(crypto.randomUUID(), signature),
      otherKey.shared(version.id, signature),
    ])
      await expect(attempt).rejects.toMatchObject({ code: "not_found" });

    await db.database
      .update(workspaces)
      .set({ archivedAt: new Date() })
      .where(eq(workspaces.id, member.workspaceId));
    await expect(shares.shared(version.id, signature)).rejects.toMatchObject({
      code: "not_found",
    });
  });

  it("only gives links to workspace members", async () => {
    const { member, shares, key } = await setup();
    const viewerId = await seedUser(db.database);
    await db.database.insert(organizationMembers).values({
      organizationId: member.organizationId,
      userId: viewerId,
      role: "member",
      status: "active",
    });

    expect(await shares.get(viewerId, ...key)).toEqual(
      await shares.get(member.userId, ...key),
    );
    await expect(
      shares.get(await seedUser(db.database), ...key),
    ).rejects.toBeTruthy();
  });

  it("is unavailable without a key", async () => {
    const { member, key } = await setup();
    await expect(
      createReportShares(db.database).get(member.userId, ...key),
    ).rejects.toMatchObject({ code: "unavailable" });
  });
});
