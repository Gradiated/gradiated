import { eq, sql } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { organizations } from "../src/db/schema/index.js";
import {
  createOrganizationService,
  type OrganizationService,
} from "../src/organizations/service.js";
import { seedMember } from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

const nda = {
  document_id: "nda-document",
  template_version: "v1",
  signed_at: "2026-11-06T12:00:00.000Z",
};

describe("organization onboarding metadata", () => {
  let db: TestDatabase;
  let service: OrganizationService;

  beforeAll(async () => {
    db = await createTestDatabase();
    service = createOrganizationService(db.database);
  });
  afterAll(() => db.dispose());

  const metadata = async (organizationId: string) => {
    const [row] = await db.database
      .select({ metadata: organizations.metadata })
      .from(organizations)
      .where(eq(organizations.id, organizationId));

    return row?.metadata;
  };

  it("starts empty and records the NDA once per template version", async () => {
    const { userId, organizationId } = await seedMember(db.database, {
      role: "admin",
    });
    expect(await service.getOnboarding(userId, organizationId)).toEqual({});

    await service.recordOnboardingNda(userId, organizationId, nda);
    expect(
      await service.recordOnboardingNda(userId, organizationId, {
        ...nda,
        document_id: "another-document",
      }),
    ).toEqual({ nda });
    expect(
      await service.recordOnboardingNda(userId, organizationId, {
        ...nda,
        document_id: "new-template-document",
        template_version: "v2",
      }),
    ).toMatchObject({
      nda: { document_id: "new-template-document", template_version: "v2" },
    });
  });

  it("submits once and keeps unrelated onboarding fields", async () => {
    const { userId, organizationId } = await seedMember(db.database, {
      role: "admin",
    });
    await service.recordOnboardingNda(userId, organizationId, nda);

    const first = await service.submitOnboarding(
      userId,
      organizationId,
      "slack",
    );
    const repeated = await service.submitOnboarding(
      userId,
      organizationId,
      "email",
    );

    expect(first).toEqual({
      submitted: true,
      onboarding: {
        nda,
        submitted_at: expect.any(String),
        submitted_by: userId,
        contact_channel: "slack",
      },
    });
    expect(repeated).toEqual({
      submitted: false,
      onboarding: first.onboarding,
    });
    expect(await metadata(organizationId)).toEqual({
      schema_version: 1,
      training_onboarding: first.onboarding,
    });
  });

  it("merges a new NDA without clearing the submission", async () => {
    const { userId, organizationId } = await seedMember(db.database, {
      role: "admin",
    });
    const { onboarding } = await service.submitOnboarding(
      userId,
      organizationId,
      "email",
    );

    const updated = await service.recordOnboardingNda(
      userId,
      organizationId,
      nda,
    );

    expect(updated).toEqual({ ...onboarding, nda });
  });

  it("rejects metadata outside the closed schema", async () => {
    const { userId, organizationId } = await seedMember(db.database, {
      role: "admin",
    });
    await db.database
      .update(organizations)
      .set({
        metadata: sql`${organizations.metadata} || '{"unknown":true}'::jsonb`,
      })
      .where(eq(organizations.id, organizationId));

    await expect(
      service.getOnboarding(userId, organizationId),
    ).rejects.toThrow();
  });

  it("requires an organization admin", async () => {
    const { userId, organizationId } = await seedMember(db.database, {
      role: "member",
    });

    await expect(
      service.submitOnboarding(userId, organizationId, "email"),
    ).rejects.toMatchObject({ code: "forbidden" });
  });
});
