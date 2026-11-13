import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { integrations } from "../src/db/schema/index.js";
import {
  createIntegrationService,
  type IntegrationService,
} from "../src/integrations/service.js";
import { seedMember } from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

const channelId = () =>
  `C${Math.random().toString(36).slice(2, 12).toUpperCase()}`;

describe("organization integrations", () => {
  let db: TestDatabase;
  let service: IntegrationService;

  beforeAll(async () => {
    db = await createTestDatabase();
    service = createIntegrationService(db.database);
  });
  afterAll(() => db.dispose());

  const admin = () => seedMember(db.database, { role: "admin" });

  it("keeps one Slack channel per organization until it is revoked", async () => {
    const { userId, organizationId } = await admin();
    const first = await service.recordSlackChannel(userId, organizationId, {
      id: channelId(),
      name: "ext-acme-gradiated",
    });

    expect(first).toMatchObject({
      provider: "slack",
      status: "pending",
      settings: { schema_version: 1, channel_name: "ext-acme-gradiated" },
    });
    await expect(
      service.recordSlackChannel(userId, organizationId, {
        id: channelId(),
        name: "ext-acme-two-gradiated",
      }),
    ).rejects.toMatchObject({ code: "conflict" });
    expect(await service.findSlackChannel(userId, organizationId)).toEqual(
      first,
    );

    await service.revoke(userId, organizationId, first.id);
    expect(
      await service.findSlackChannel(userId, organizationId),
    ).toBeUndefined();
    await expect(
      service.recordSlackChannel(userId, organizationId, {
        id: channelId(),
        name: "ext-acme-gradiated",
      }),
    ).resolves.toMatchObject({ status: "pending" });
  });

  it("does not let two organizations claim the same Slack channel", async () => {
    const shared = channelId();
    const first = await admin();
    const second = await admin();
    await service.recordSlackChannel(first.userId, first.organizationId, {
      id: shared,
      name: "ext-acme-gradiated",
    });

    await expect(
      service.recordSlackChannel(second.userId, second.organizationId, {
        id: shared,
        name: "ext-acme-gradiated",
      }),
    ).rejects.toMatchObject({ code: "conflict" });
  });

  it("allows one Slack invitation per cooldown and restores a failed claim", async () => {
    const { userId, organizationId } = await admin();
    const channel = await service.recordSlackChannel(userId, organizationId, {
      id: channelId(),
      name: "ext-acme-gradiated",
    });
    const claim = await service.claimSlackInvitation(userId, organizationId, {
      email: "ada@acme.test",
      cooldownMs: 600_000,
    });
    if (!claim.claimed)
      throw new Error("The first invitation was not claimed.");

    expect(claim.integration.settings).toMatchObject({
      invited_email: "ada@acme.test",
      invited_at: expect.any(String),
    });
    const repeated = await service.claimSlackInvitation(
      userId,
      organizationId,
      { email: "grace@acme.test", cooldownMs: 600_000 },
    );
    expect(repeated).toEqual({
      claimed: false,
      availableAt: new Date(
        Date.parse(claim.integration.settings.invited_at!) + 600_000,
      ),
    });

    await service.releaseSlackInvitation(userId, organizationId, claim);
    const [row] = await db.database
      .select({ settings: integrations.settings })
      .from(integrations)
      .where(eq(integrations.id, channel.id));
    expect(row?.settings).toEqual({
      schema_version: 1,
      channel_name: "ext-acme-gradiated",
    });
    await expect(
      service.claimSlackInvitation(userId, organizationId, {
        email: "grace@acme.test",
        cooldownMs: 600_000,
      }),
    ).resolves.toMatchObject({ claimed: true });
    await expect(
      service.activate(userId, organizationId, channel.id),
    ).resolves.toMatchObject({ status: "active" });
  });

  it("records several GitHub installations and refreshes a repeated one", async () => {
    const { userId, organizationId } = await admin();
    const id = Math.floor(Math.random() * 1_000_000_000) + 1;
    const first = await service.recordGithubInstallation(
      userId,
      organizationId,
      { id, account_login: "acme", repository_selection: "selected" },
    );
    const refreshed = await service.recordGithubInstallation(
      userId,
      organizationId,
      { id, account_login: "acme-renamed", repository_selection: "all" },
    );
    await service.recordGithubInstallation(userId, organizationId, {
      id: id + 1,
      account_login: "acme-labs",
      repository_selection: "all",
    });

    expect(refreshed).toMatchObject({
      id: first.id,
      externalId: String(id),
      status: "active",
      settings: { account_login: "acme-renamed", repository_selection: "all" },
    });
    expect(
      (await service.list(userId, organizationId)).map(
        (integration) => integration.externalId,
      ),
    ).toEqual([String(id), String(id + 1)]);

    const other = await admin();
    await expect(
      service.recordGithubInstallation(other.userId, other.organizationId, {
        id,
        account_login: "acme",
        repository_selection: "all",
      }),
    ).rejects.toMatchObject({ code: "conflict" });
  });

  it("requires an organization admin", async () => {
    const { userId, organizationId } = await seedMember(db.database, {
      role: "member",
    });

    await expect(service.list(userId, organizationId)).rejects.toMatchObject({
      code: "forbidden",
    });
  });
});
