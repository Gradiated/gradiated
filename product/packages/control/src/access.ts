import { and, eq } from "drizzle-orm";

import type { ControlDatabase } from "./db/client.js";
import {
  organizationMembers,
  organizations,
  workspaces,
  type OrganizationRole,
  type OrganizationStatus,
} from "./db/schema/index.js";
import { ControlServiceError } from "./errors.js";

export type Membership = {
  role: OrganizationRole;
  organizationStatus: OrganizationStatus;
};

type MembershipKey = { userId: string; organizationId: string };

const membershipColumns = {
  role: organizationMembers.role,
  organizationStatus: organizations.status,
};

export const activeCustomerMember = ({
  userId,
  organizationId,
}: {
  userId: string;
  organizationId?: string | undefined;
}) =>
  and(
    eq(organizationMembers.userId, userId),
    organizationId === undefined
      ? undefined
      : eq(organizationMembers.organizationId, organizationId),
    eq(organizationMembers.status, "active"),
    eq(organizations.kind, "customer"),
  );

export const findMembership = async (
  database: ControlDatabase,
  key: MembershipKey,
): Promise<Membership | undefined> => {
  const [membership] = await database
    .select(membershipColumns)
    .from(organizationMembers)
    .innerJoin(
      organizations,
      eq(organizations.id, organizationMembers.organizationId),
    )
    .where(activeCustomerMember(key))
    .limit(1);

  return membership;
};

export const requireMembership = async (
  database: ControlDatabase,
  key: MembershipKey,
): Promise<Membership> => {
  const membership = await findMembership(database, key);
  if (!membership) {
    throw new ControlServiceError(
      "not_found",
      "The organization does not exist or is not accessible.",
    );
  }

  return membership;
};

export const requireWorkspaceMembership = async (
  database: ControlDatabase,
  key: MembershipKey & { workspaceId: string },
): Promise<{
  membership: Membership;
  workspace: typeof workspaces.$inferSelect;
}> => {
  const [row] = await database
    .select({ ...membershipColumns, workspace: workspaces })
    .from(organizationMembers)
    .innerJoin(
      organizations,
      eq(organizations.id, organizationMembers.organizationId),
    )
    .innerJoin(
      workspaces,
      and(
        eq(workspaces.organizationId, organizationMembers.organizationId),
        eq(workspaces.id, key.workspaceId),
      ),
    )
    .where(activeCustomerMember(key))
    .limit(1);
  if (!row) {
    throw new ControlServiceError(
      "not_found",
      "The workspace does not exist or is not accessible.",
    );
  }

  const { workspace, ...membership } = row;

  return { membership, workspace };
};
