import { and, eq } from "drizzle-orm";
import {
  CurrentOrganizationSchema,
  UpdateOrganizationSchema,
  UuidSchema,
  type UpdateOrganization,
} from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import {
  organizations,
  organizationMembers,
  workspaces,
} from "../db/schema/index.js";
import { activeCustomerMember } from "../access.js";

const OrganizationRecordSchema = CurrentOrganizationSchema.omit({
  default_workspace_id: true,
}).extend({ defaultWorkspaceId: UuidSchema });

export const createOrganizationStore = (database: ControlDatabase) => ({
  async updateName(
    userId: string,
    organizationId: string,
    input: UpdateOrganization,
  ) {
    const patch = UpdateOrganizationSchema.parse(input);

    await database
      .update(organizations)
      .set({ name: patch.name, updatedAt: new Date() })
      .where(eq(organizations.id, organizationId));

    const [row] = await database
      .select({
        id: organizations.id,
        name: organizations.name,
        status: organizations.status,
        role: organizationMembers.role,
        defaultWorkspaceId: workspaces.id,
      })
      .from(organizations)
      .innerJoin(
        organizationMembers,
        eq(organizationMembers.organizationId, organizations.id),
      )
      .innerJoin(
        workspaces,
        and(
          eq(workspaces.organizationId, organizations.id),
          eq(workspaces.isDefault, true),
        ),
      )
      .where(activeCustomerMember({ userId, organizationId }));

    return row ? OrganizationRecordSchema.parse(row) : undefined;
  },
});
