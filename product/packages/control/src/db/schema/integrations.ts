import { sql } from "drizzle-orm";
import {
  check,
  index,
  jsonb,
  pgTable,
  text,
  timestamp,
  uniqueIndex,
  uuid,
} from "drizzle-orm/pg-core";

import {
  INTEGRATION_PROVIDERS,
  INTEGRATION_STATUSES,
  type GithubIntegrationSettings,
  type SlackIntegrationSettings,
} from "@gradiated/contracts";

import { users } from "./auth.js";
import { organizations } from "./organizations.js";

export const integrations = pgTable(
  "integrations",
  {
    id: uuid("id").primaryKey(),
    organizationId: uuid("organization_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    provider: text("provider", { enum: INTEGRATION_PROVIDERS }).notNull(),
    externalId: text("external_id").notNull(),
    status: text("status", { enum: INTEGRATION_STATUSES }).notNull(),
    settings: jsonb("settings")
      .$type<SlackIntegrationSettings | GithubIntegrationSettings>()
      .notNull(),
    createdBy: uuid("created_by")
      .notNull()
      .references(() => users.id, { onDelete: "restrict" }),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
  },
  (table) => [
    uniqueIndex("integrations_provider_external_id_unique")
      .on(table.provider, table.externalId)
      .where(sql`${table.status} <> 'revoked'`),
    uniqueIndex("integrations_organization_slack_unique")
      .on(table.organizationId)
      .where(sql`${table.provider} = 'slack' and ${table.status} <> 'revoked'`),
    index("integrations_organization_id_index").on(table.organizationId),
    check(
      "integrations_provider_check",
      sql`${table.provider} in ('github', 'slack')`,
    ),
    check(
      "integrations_status_check",
      sql`${table.status} in ('pending', 'active', 'revoked')`,
    ),
  ],
);
