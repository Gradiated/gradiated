import {
  BalanceTransactionQuerySchema,
  BalanceTransactionSchema,
  UuidSchema,
  type BalanceTransactionQuery,
} from "@gradiated/contracts";
import { and, desc, eq, inArray, sql } from "drizzle-orm";
import { z } from "zod";

import type { ControlDatabase } from "../db/client.js";
import {
  ORGANIZATION_STATUSES,
  balanceTransactions,
  organizations,
  workspaces,
} from "../db/schema/index.js";

const BalanceTransactionRecordSchema = z.object({
  id: UuidSchema,
  organizationId: UuidSchema,
  type: BalanceTransactionSchema.shape.type,
  amount: z.bigint(),
  balanceAfter: z.bigint(),
  sourceType: BalanceTransactionSchema.shape.source_type,
  sourceId: z.string(),
  periodStart: z.date().nullable(),
  periodEnd: z.date().nullable(),
  generationCount: z.bigint().nullable(),
  createdBy: UuidSchema.nullable(),
  createdAt: z.date(),
});

export const listBalanceTransactionPage = async (
  database: ControlDatabase,
  organizationId: string,
  query: Partial<BalanceTransactionQuery>,
) => {
  const { limit, cursor } = BalanceTransactionQuerySchema.parse(query);
  const anchor = cursor
    ? database
        .select({
          createdAt: balanceTransactions.createdAt,
          id: balanceTransactions.id,
        })
        .from(balanceTransactions)
        .where(
          and(
            eq(balanceTransactions.organizationId, organizationId),
            eq(balanceTransactions.id, cursor),
          ),
        )
    : undefined;
  const records = await database
    .select()
    .from(balanceTransactions)
    .where(
      and(
        eq(balanceTransactions.organizationId, organizationId),
        anchor
          ? sql`(${balanceTransactions.createdAt}, ${balanceTransactions.id}) < (${anchor})`
          : undefined,
      ),
    )
    .orderBy(desc(balanceTransactions.createdAt), desc(balanceTransactions.id))
    .limit(limit + 1);
  const data = records
    .slice(0, limit)
    .map((record) => BalanceTransactionRecordSchema.parse(record));

  return { data, nextCursor: records.length > limit ? data.at(-1)!.id : null };
};

const WorkspaceOwnerRecordSchema = z.object({
  workspaceId: UuidSchema,
  organizationId: UuidSchema,
  organizationStatus: z.enum(ORGANIZATION_STATUSES),
  archivedAt: z.date().nullable(),
});

export type WorkspaceOwnerRecord = z.infer<typeof WorkspaceOwnerRecordSchema>;

export const readCustomerWorkspaceOwners = async (
  database: ControlDatabase,
  workspaceIds: string[],
): Promise<Map<string, WorkspaceOwnerRecord>> => {
  const rows = await database
    .select({
      workspaceId: workspaces.id,
      organizationId: organizations.id,
      organizationStatus: organizations.status,
      archivedAt: workspaces.archivedAt,
    })
    .from(workspaces)
    .innerJoin(organizations, eq(organizations.id, workspaces.organizationId))
    .where(
      and(
        inArray(workspaces.id, workspaceIds),
        eq(organizations.kind, "customer"),
      ),
    );

  return new Map(
    rows.map((row) => {
      const owner = WorkspaceOwnerRecordSchema.parse(row);

      return [owner.workspaceId, owner];
    }),
  );
};
