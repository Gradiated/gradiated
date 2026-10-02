import { sql } from "drizzle-orm";
import {
  check,
  foreignKey,
  jsonb,
  pgTable,
  text,
  timestamp,
  integer,
  uuid,
} from "drizzle-orm/pg-core";
import type { LoraProfile } from "@gradiated/contracts";
import { tasks, taskVersions } from "./training.js";
import { users } from "./auth.js";

export const versionHostings = pgTable(
  "version_hostings",
  {
    versionId: uuid("version_id")
      .primaryKey()
      .references(() => taskVersions.id, { onDelete: "cascade" }),
    desired: text("desired", { enum: ["hosted", "unhosted"] }).notNull(),
    revision: integer("revision").notNull().default(1),
    profile: jsonb("profile").$type<LoraProfile>().notNull(),
    stage: text("stage", {
      enum: ["pending", "ready", "failed", "draining", "unhosted"],
    }).notNull(),
    errorCode: text("error_code", {
      enum: ["preparation_failed", "capacity_unavailable"],
    }),
    requestedBy: uuid("requested_by").references(() => users.id, {
      onDelete: "set null",
    }),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    check(
      "version_hostings_desired_check",
      sql`${table.desired} in ('hosted', 'unhosted')`,
    ),
    check(
      "version_hostings_stage_check",
      sql`${table.stage} in ('pending', 'ready', 'failed', 'draining', 'unhosted')`,
    ),
    check("version_hostings_revision_check", sql`${table.revision} > 0`),
    check(
      "version_hostings_error_check",
      sql`${table.errorCode} in ('preparation_failed', 'capacity_unavailable')`,
    ),
  ],
);

export const taskPromotions = pgTable(
  "task_promotions",
  {
    id: uuid("id").primaryKey(),
    taskId: uuid("task_id").notNull(),
    workspaceId: uuid("workspace_id").notNull(),
    previousVersionId: uuid("previous_version_id"),
    versionId: uuid("version_id").notNull(),
    actorId: uuid("actor_id").references(() => users.id, {
      onDelete: "set null",
    }),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .notNull()
      .defaultNow(),
  },
  (table) => [
    foreignKey({
      columns: [table.taskId, table.workspaceId],
      foreignColumns: [tasks.id, tasks.workspaceId],
    }).onDelete("cascade"),
    foreignKey({
      columns: [table.versionId, table.taskId, table.workspaceId],
      foreignColumns: [
        taskVersions.id,
        taskVersions.taskId,
        taskVersions.workspaceId,
      ],
    }).onDelete("restrict"),
  ],
);
