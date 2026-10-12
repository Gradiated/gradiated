import { sql } from "drizzle-orm";
import {
  check,
  jsonb,
  pgTable,
  text,
  timestamp,
  uniqueIndex,
  uuid,
} from "drizzle-orm/pg-core";

import type { InstanceCertificate } from "../../instances/certificate-schema.js";

// Nomad owns device discovery and scheduling state.
export const instances = pgTable(
  "instances",
  {
    id: uuid("id").primaryKey(),
    provider: text("provider").notNull(),
    providerAccountId: text("provider_account_id").notNull(),
    providerInstanceId: text("provider_instance_id").notNull(),
    region: text("region"),
    faultDomain: text("fault_domain"),
    sku: text("sku").notNull(),
    nomadNodeId: uuid("nomad_node_id"),
    servingUrl: text("serving_url"),
    certificate: jsonb("certificate").$type<InstanceCertificate>(),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
    retiredAt: timestamp("retired_at", { withTimezone: true, mode: "date" }),
  },
  (t) => [
    uniqueIndex("instances_provider_identity_unique").on(
      t.provider,
      t.providerAccountId,
      t.providerInstanceId,
    ),
    uniqueIndex("instances_nomad_node_unique").on(t.nomadNodeId),
    check(
      "instances_identity_check",
      sql`length(${t.provider}) between 1 and 100 and length(${t.providerAccountId}) between 1 and 200 and length(${t.providerInstanceId}) between 1 and 200`,
    ),
    check("instances_sku_check", sql`length(${t.sku}) between 1 and 200`),
    check(
      "instances_serving_url_check",
      sql`${t.servingUrl} is null or ${t.servingUrl} = 'http://gpu-' || ${t.id}::text || '.tailscale-inference.svc.cluster.local:8888'`,
    ),
  ],
);
