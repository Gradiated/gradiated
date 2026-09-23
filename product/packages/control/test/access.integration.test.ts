import { afterAll, beforeAll, describe, expect, it } from "vitest";

import {
  findMembership,
  requireMembership,
  requireWorkspaceMembership,
} from "../src/access.js";
import { ORGANIZATION_ROLES } from "../src/db/schema/index.js";
import { seedMember, seedUser, type MemberSeed } from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

const organizationStatuses = ["active", "suspended"] as const;

describe("organization access", () => {
  let testDatabase: TestDatabase;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
  });

  afterAll(() => testDatabase.dispose());

  const setup = (seed: MemberSeed) => seedMember(testDatabase.database, seed);

  describe.each(ORGANIZATION_ROLES)("an active %s", (role) => {
    it.each(organizationStatuses)(
      "is a member of an organization that is %s",
      async (status) => {
        const key = await setup({ role, organization: { status } });

        const expected = { role, organizationStatus: status };

        expect(await requireMembership(testDatabase.database, key)).toEqual(
          expected,
        );
        expect(
          await requireWorkspaceMembership(testDatabase.database, key),
        ).toMatchObject({
          membership: expected,
          workspace: { id: key.workspaceId, archivedAt: null },
        });
      },
    );
  });

  it("returns an archived workspace to its member", async () => {
    const key = await setup({ role: "member", workspace: { archived: true } });

    const { workspace } = await requireWorkspaceMembership(
      testDatabase.database,
      key,
    );

    expect(workspace.archivedAt).toBeInstanceOf(Date);
  });

  it.each<[string, () => Promise<Awaited<ReturnType<typeof setup>>>]>([
    [
      "a suspended member",
      () => setup({ role: "owner", memberStatus: "suspended" }),
    ],
    [
      "a non-member",
      async () => ({
        ...(await setup({ role: "owner" })),
        userId: await seedUser(testDatabase.database),
      }),
    ],
    [
      "a member of a distribution channel",
      () =>
        setup({
          role: "owner",
          organization: { kind: "distribution_channel" },
        }),
    ],
  ])("hides the organization and workspace from %s", async (_name, seed) => {
    const key = await seed();

    expect(await findMembership(testDatabase.database, key)).toBeUndefined();
    await expect(
      requireMembership(testDatabase.database, key),
    ).rejects.toMatchObject({
      code: "not_found",
      message: "The organization does not exist or is not accessible.",
    });
    await expect(
      requireWorkspaceMembership(testDatabase.database, key),
    ).rejects.toMatchObject({
      code: "not_found",
      message: "The workspace does not exist or is not accessible.",
    });
  });

  it("hides a workspace of another organization", async () => {
    const key = await setup({ role: "owner" });
    const other = await setup({ role: "owner" });

    await expect(
      requireWorkspaceMembership(testDatabase.database, {
        ...key,
        workspaceId: other.workspaceId,
      }),
    ).rejects.toMatchObject({ code: "not_found" });
  });
});
