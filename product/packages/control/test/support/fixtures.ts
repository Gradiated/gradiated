import { randomUUID } from "node:crypto";

import type {
  ModelDeploymentRelease,
  ModelPropertiesInput,
} from "@gradiated/contracts";

import { asc, eq, sql } from "drizzle-orm";

import type { CatalogService } from "../../src/catalog/service.js";
import type { ControlDatabase } from "../../src/db/client.js";
import {
  balanceTransactions,
  billingAccounts,
  organizationMembers,
  organizationSlugs,
  organizations,
  users,
  workspaces,
  type BILLING_MODES,
  type MEMBER_STATUSES,
  type OrganizationKind,
  type OrganizationRole,
  type OrganizationStatus,
} from "../../src/db/schema/index.js";

export type OrganizationSeed = {
  kind?: OrganizationKind;
  status?: OrganizationStatus;
  members?: {
    userId: string;
    role: OrganizationRole;
    status?: (typeof MEMBER_STATUSES)[number];
  }[];
  billing?: { mode: (typeof BILLING_MODES)[number]; balance: bigint };
};

export const seedUser = async (
  database: ControlDatabase,
  seed: { email?: string; emailVerified?: boolean } = {},
): Promise<string> => {
  const id = randomUUID();

  await database.insert(users).values({
    id,
    name: "Test user",
    email: seed.email ?? `${id}@example.test`,
    emailVerified: seed.emailVerified ?? false,
  });

  return id;
};

export const seedOrganization = async (
  database: ControlDatabase,
  seed: OrganizationSeed = {},
): Promise<string> => {
  const id = randomUUID();

  await database.insert(organizations).values({
    id,
    kind: seed.kind ?? "customer",
    name: `Organization ${id}`,
    status: seed.status ?? "active",
  });
  await database.insert(organizationSlugs).values({
    slug: `org-${id.replaceAll("-", "")}`,
    organizationId: id,
    isCurrent: true,
  });

  for (const member of seed.members ?? []) {
    await database.insert(organizationMembers).values({
      organizationId: id,
      userId: member.userId,
      role: member.role,
      status: member.status ?? "active",
    });
  }

  if (seed.billing) {
    await database
      .insert(billingAccounts)
      .values({ organizationId: id, ...seed.billing });
  }

  return id;
};

export const billingAccountRow = async (
  database: ControlDatabase,
  organizationId: string,
) => {
  const [row] = await database
    .select()
    .from(billingAccounts)
    .where(eq(billingAccounts.organizationId, organizationId));

  return row;
};

export const ledgerRows = (database: ControlDatabase, organizationId: string) =>
  database
    .select()
    .from(balanceTransactions)
    .where(eq(balanceTransactions.organizationId, organizationId))
    .orderBy(asc(balanceTransactions.createdAt), asc(balanceTransactions.id));

/** The organization of a workspace, for task and version rows in tests. */
export const workspaceOrganization = (workspaceId: string) =>
  sql<string>`(select ${workspaces.organizationId} from ${workspaces} where ${workspaces.id} = ${workspaceId})`;

export const seedWorkspace = async (
  database: ControlDatabase,
  seed: { organizationId: string; archived?: boolean; isDefault?: boolean },
): Promise<string> => {
  const id = randomUUID();

  await database.insert(workspaces).values({
    id,
    organizationId: seed.organizationId,
    name: `Workspace ${id}`,
    isDefault: seed.isDefault ?? false,
    archivedAt: seed.archived ? new Date() : null,
  });

  return id;
};

export type MemberSeed = {
  role: OrganizationRole;
  memberStatus?: (typeof MEMBER_STATUSES)[number];
  organization?: Omit<OrganizationSeed, "members">;
  workspace?: { archived?: boolean };
};

export const seedMember = async (
  database: ControlDatabase,
  seed: MemberSeed,
): Promise<{ userId: string; organizationId: string; workspaceId: string }> => {
  const userId = await seedUser(database);
  const organizationId = await seedOrganization(database, {
    ...seed.organization,
    members: [
      { userId, role: seed.role, status: seed.memberStatus ?? "active" },
    ],
  });
  const workspaceId = await seedWorkspace(database, {
    organizationId,
    ...seed.workspace,
  });

  return { userId, organizationId, workspaceId };
};

type ModelInput = Parameters<CatalogService["upsertModel"]>[0];
type DeploymentInput = Parameters<CatalogService["upsertModelDeployment"]>[0];

export const modelProperties = (): ModelPropertiesInput => ({
  description: "Test model.",
  input_modalities: [
    {
      type: "text",
      supported_inputs: { max_context_length: { value: 8_192, unit: "token" } },
      pricing: [{ type: "prompt", unit: "token", cost: 2 }],
    },
  ],
  output_modalities: [
    {
      type: "text",
      max_length: { value: 512, unit: "token" },
      pricing: [{ type: "completion", unit: "token", cost: 4 }],
    },
  ],
});

export const modelInput = (
  overrides: Partial<ModelInput> = {},
): ModelInput => ({
  id: `test/${randomUUID()}`,
  name: "Test model",
  status: "available",
  properties: modelProperties(),
  ...overrides,
});

export const deploymentRelease = (): ModelDeploymentRelease => ({
  schema_version: 1,
  runtime_revision: "runtime-revision",
  model_path: "vendor/model",
  model_revision: "model-revision",
  tokenizer_path: "vendor/tokenizer",
  tokenizer_revision: "tokenizer-revision",
});

export const deploymentInput = (
  modelId: string,
  overrides: Partial<DeploymentInput> = {},
): DeploymentInput => ({
  id: randomUUID(),
  modelId,
  status: "available",
  provider: "runpod",
  region: "eu-west",
  faultDomain: "eu-west/rack-1",
  serviceUrl: "https://runtime.example.test",
  release: deploymentRelease(),
  ...overrides,
});
