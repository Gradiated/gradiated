import { and, asc, eq } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";

import type { ControlDatabase } from "../db/client.js";
import {
  billingAccounts,
  organizationMembers,
  organizations,
  workspaces,
} from "../db/schema/index.js";
import {
  ControlServiceError,
  type ServingProjector,
  type WorkspaceRecord,
} from "../workspaces/service.js";

export type OrganizationRole = "owner" | "admin" | "billing" | "member";

export interface UserOrganization {
  id: string;
  name: string;
  status: "active" | "suspended";
  role: OrganizationRole;
  defaultWorkspaceId: string;
}

export interface CreatedOrganization {
  id: string;
  kind: "customer";
  name: string;
  status: "active";
  role: "owner";
  defaultWorkspaceId: string;
  createdAt: Date;
  updatedAt: Date;
}

export interface OrganizationService {
  listForUser(userId: string): Promise<UserOrganization[]>;
  createForUser(userId: string, name: string): Promise<CreatedOrganization>;
}

export function createOrganizationService(
  database: ControlDatabase,
  projector: ServingProjector,
): OrganizationService {
  return {
    async listForUser(userId) {
      const rows = await database
        .select({
          id: organizations.id,
          name: organizations.name,
          status: organizations.status,
          role: organizationMembers.role,
          defaultWorkspaceId: workspaces.id,
        })
        .from(organizationMembers)
        .innerJoin(
          organizations,
          eq(organizations.id, organizationMembers.organizationId),
        )
        .innerJoin(
          workspaces,
          and(
            eq(workspaces.organizationId, organizations.id),
            eq(workspaces.isDefault, true),
          ),
        )
        .where(
          and(
            eq(organizationMembers.userId, userId),
            eq(organizationMembers.status, "active"),
            eq(organizations.kind, "customer"),
          ),
        )
        .orderBy(asc(organizations.createdAt), asc(organizations.id));

      return rows.map((row) => ({
        ...row,
        status: row.status as UserOrganization["status"],
        role: row.role as OrganizationRole,
      }));
    },

    async createForUser(userId, name) {
      const organizationId = uuidv7();
      const workspaceId = uuidv7();
      const now = new Date();

      await database.transaction(async (transaction) => {
        await transaction.insert(organizations).values({
          id: organizationId,
          kind: "customer",
          name,
          status: "active",
          createdAt: now,
          updatedAt: now,
        });
        await transaction.insert(organizationMembers).values({
          organizationId,
          userId,
          role: "owner",
          status: "active",
          createdAt: now,
          updatedAt: now,
        });
        await transaction.insert(workspaces).values({
          id: workspaceId,
          organizationId,
          name: "Default",
          isDefault: true,
          createdAt: now,
          updatedAt: now,
        });
        await transaction.insert(billingAccounts).values({
          organizationId,
          mode: "prepaid",
          balance: 0n,
          createdAt: now,
          updatedAt: now,
        });
      });

      try {
        await projector.initializeAccount({
          organizationId,
          organizationKind: "customer",
          organizationStatus: "active",
          billingMode: "prepaid",
          balance: 0n,
        });
        const workspace: WorkspaceRecord = {
          id: workspaceId,
          organizationId,
          name: "Default",
          isDefault: true,
          archivedAt: null,
          createdAt: now,
          updatedAt: now,
        };
        await projector.projectWorkspace(workspace);
      } catch (error) {
        throw new ControlServiceError(
          "unavailable",
          "The organization was created, but serving state is not yet available.",
          error,
        );
      }

      return {
        id: organizationId,
        kind: "customer",
        name,
        status: "active",
        role: "owner",
        defaultWorkspaceId: workspaceId,
        createdAt: now,
        updatedAt: now,
      };
    },
  };
}
