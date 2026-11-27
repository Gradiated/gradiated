import { sql } from "drizzle-orm";
import {
  bigint,
  boolean,
  check,
  customType,
  foreignKey,
  index,
  jsonb,
  pgTable,
  primaryKey,
  smallint,
  text,
  timestamp,
  unique,
  uniqueIndex,
  uuid,
} from "drizzle-orm/pg-core";

import {
  DEFAULT_EVALUATION_JUDGE,
  type EvaluationJudge,
  type ModelDeploymentRelease,
  type ModelProperties,
  type OrganizationMetadata,
} from "@gradiated/contracts";

import { users } from "./auth.js";
import { instances } from "./instances.js";

export const ORGANIZATION_KINDS = ["customer", "distribution_channel"] as const;
export const ORGANIZATION_STATUSES = ["active", "suspended"] as const;
export const ORGANIZATION_ROLES = ["admin", "member"] as const;
export const MEMBER_STATUSES = ["active", "suspended"] as const;
export const BILLING_MODES = ["prepaid", "invoiced"] as const;
export const MODEL_STATUSES = ["available", "unavailable", "retired"] as const;
/** The inference interface: chat generates text; decision answers SystemOne. */
export const MODEL_TYPES = ["chat", "decision"] as const;
export const DEPLOYMENT_STATUSES = [
  "available",
  "unavailable",
  "draining",
] as const;
export const BALANCE_TRANSACTION_TYPES = [
  "topup",
  "usage",
  "refund",
  "chargeback",
  "credit",
  "payment",
  "adjustment",
] as const;
export const BALANCE_SOURCE_TYPES = [
  "stripe_checkout_session",
  "stripe_refund",
  "stripe_dispute",
  "generation_settlement_batch",
  "openrouter_payment",
  "operator",
  "stripe_invoice",
] as const;
export const TOP_UP_CHARGE_REASONS = ["top_up", "auto_top_up"] as const;
export const TOP_UP_CHARGE_STATUSES = [
  "pending",
  "succeeded",
  "failed",
] as const;
export const TOP_UP_METHODS = ["card", "checkout"] as const;

export type OrganizationKind = (typeof ORGANIZATION_KINDS)[number];
export type OrganizationStatus = (typeof ORGANIZATION_STATUSES)[number];
export type OrganizationRole = (typeof ORGANIZATION_ROLES)[number];

const bytea = customType<{ data: Buffer }>({
  dataType() {
    return "bytea";
  },
});

export const organizations = pgTable(
  "organizations",
  {
    id: uuid("id").primaryKey(),
    kind: text("kind", { enum: ORGANIZATION_KINDS }).notNull(),
    name: text("name").notNull(),
    // Prefixes private model names. New organizations start with a random
    // placeholder and choose theirs in onboarding; it is fixed once they have a model.
    slug: text("slug")
      .notNull()
      .unique("organizations_slug_unique")
      .default(sql`left(md5(gen_random_uuid()::text), 16)`),
    status: text("status", { enum: ORGANIZATION_STATUSES }).notNull(),
    autoJoinDomain: text("auto_join_domain"),
    onboardedAt: timestamp("onboarded_at", {
      withTimezone: true,
      mode: "date",
    }),
    metadata: jsonb("metadata")
      .$type<OrganizationMetadata>()
      .default({ schema_version: 1 })
      .notNull(),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
  },
  (table) => [
    uniqueIndex("organizations_auto_join_domain_unique").on(
      table.autoJoinDomain,
    ),
    check(
      "organizations_kind_check",
      sql`${table.kind} in ('customer', 'distribution_channel')`,
    ),
    check(
      "organizations_status_check",
      sql`${table.status} in ('active', 'suspended')`,
    ),
    check(
      "organizations_slug_check",
      sql`${table.slug} ~ '^[a-z0-9][a-z0-9-]{0,37}[a-z0-9]$'`,
    ),
  ],
);

export const organizationMembers = pgTable(
  "organization_members",
  {
    organizationId: uuid("organization_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "restrict" }),
    role: text("role", { enum: ORGANIZATION_ROLES }).notNull(),
    status: text("status", { enum: MEMBER_STATUSES }).notNull(),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
  },
  (table) => [
    primaryKey({ columns: [table.organizationId, table.userId] }),
    check(
      "organization_members_role_check",
      sql`${table.role} in ('admin', 'member')`,
    ),
    check(
      "organization_members_status_check",
      sql`${table.status} in ('active', 'suspended')`,
    ),
    index("organization_members_user_id_index").on(table.userId),
  ],
);

export const invitations = pgTable(
  "invitations",
  {
    id: uuid("id").primaryKey(),
    organizationId: uuid("organization_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    email: text("email").notNull(),
    role: text("role", { enum: ORGANIZATION_ROLES }).notNull(),
    tokenDigest: bytea("token_digest").notNull(),
    expiresAt: timestamp("expires_at", {
      withTimezone: true,
      mode: "date",
    }).notNull(),
    acceptedAt: timestamp("accepted_at", { withTimezone: true, mode: "date" }),
    revokedAt: timestamp("revoked_at", { withTimezone: true, mode: "date" }),
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
    uniqueIndex("invitations_token_digest_unique").on(table.tokenDigest),
    uniqueIndex("invitations_pending_email_unique")
      .on(table.organizationId, table.email)
      .where(sql`${table.acceptedAt} is null and ${table.revokedAt} is null`),
    index("invitations_pending_email_index")
      .on(table.email)
      .where(sql`${table.acceptedAt} is null and ${table.revokedAt} is null`),
    check("invitations_role_check", sql`${table.role} in ('admin', 'member')`),
    check(
      "invitations_email_normalized_check",
      sql`${table.email} = lower(btrim(${table.email}))`,
    ),
    check(
      "invitations_single_outcome_check",
      sql`${table.acceptedAt} is null or ${table.revokedAt} is null`,
    ),
  ],
);

export const workspaces = pgTable(
  "workspaces",
  {
    id: uuid("id").primaryKey(),
    organizationId: uuid("organization_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    name: text("name").notNull(),
    isDefault: boolean("is_default").notNull(),
    archivedAt: timestamp("archived_at", { withTimezone: true, mode: "date" }),
    traceCaptureEnabled: boolean("trace_capture_enabled")
      .notNull()
      .default(true),
    traceRetentionDays: smallint("trace_retention_days").notNull().default(180),
    defaultJudgeModel: text("default_judge_model")
      .$type<EvaluationJudge>()
      .notNull()
      .default(DEFAULT_EVALUATION_JUDGE),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
  },
  (table) => [
    check(
      "workspaces_trace_retention_days_check",
      sql`${table.traceRetentionDays} in (30, 90, 180)`,
    ),
    unique("workspaces_organization_id_id_unique").on(
      table.organizationId,
      table.id,
    ),
    uniqueIndex("workspaces_organization_name_lower_unique").on(
      table.organizationId,
      sql`lower(${table.name})`,
    ),
    uniqueIndex("workspaces_one_default_per_organization")
      .on(table.organizationId)
      .where(sql`${table.isDefault} = true`),
    check(
      "workspaces_default_not_archived_check",
      sql`not (${table.isDefault} and ${table.archivedAt} is not null)`,
    ),
  ],
);

// The auth_principals_v1 view (migration 0038) reads this table, so changing
// a column it selects needs a new view version.
export const apiKeys = pgTable(
  "api_keys",
  {
    id: uuid("id").primaryKey(),
    organizationId: uuid("organization_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    workspaceId: uuid("workspace_id").notNull(),
    name: text("name").notNull(),
    digest: bytea("digest").notNull(),
    expiresAt: timestamp("expires_at", { withTimezone: true, mode: "date" }),
    revokedAt: timestamp("revoked_at", { withTimezone: true, mode: "date" }),
    hidden: boolean("hidden").default(false).notNull(),
    // Null or empty grants the creator's role in full; a list narrows it.
    scopes: text("scopes").array(),
    createdBy: uuid("created_by").references(() => users.id, {
      onDelete: "restrict",
    }),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
  },
  (table) => [
    foreignKey({
      columns: [table.organizationId, table.workspaceId],
      foreignColumns: [workspaces.organizationId, workspaces.id],
      name: "api_keys_workspace_foreign_key",
    }).onDelete("cascade"),
    uniqueIndex("api_keys_digest_unique").on(table.digest),
    // Each member has one hidden key per purpose, such as the playground or MCP.
    uniqueIndex("api_keys_hidden_owner_name_unique")
      .on(table.workspaceId, table.createdBy, table.name)
      .where(sql`${table.hidden}`),
    index("api_keys_workspace_created_at_index").on(
      table.organizationId,
      table.workspaceId,
      table.createdAt,
      table.id,
    ),
    check(
      "api_keys_name_length_check",
      sql`char_length(${table.name}) between 1 and 200`,
    ),
    check(
      "api_keys_expiry_after_creation_check",
      sql`${table.expiresAt} is null or ${table.expiresAt} > ${table.createdAt}`,
    ),
  ],
);

export const billingAccounts = pgTable(
  "billing_accounts",
  {
    organizationId: uuid("organization_id")
      .primaryKey()
      .references(() => organizations.id, { onDelete: "cascade" }),
    mode: text("mode", { enum: BILLING_MODES }).notNull(),
    stripeCustomerId: text("stripe_customer_id"),
    balance: bigint("balance", { mode: "bigint" }).notNull(),
    stripePaymentMethodId: text("stripe_payment_method_id"),
    autoTopUpEnabled: boolean("auto_top_up_enabled").default(false).notNull(),
    autoTopUpThreshold: bigint("auto_top_up_threshold", {
      mode: "bigint",
    }),
    autoTopUpAmount: bigint("auto_top_up_amount", { mode: "bigint" }),
    // When an admin last saved auto top-up settings; earlier failures are
    // no longer reported.
    autoTopUpUpdatedAt: timestamp("auto_top_up_updated_at", {
      withTimezone: true,
      mode: "date",
    }),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
  },
  (table) => [
    uniqueIndex("billing_accounts_stripe_customer_id_unique")
      .on(table.stripeCustomerId)
      .where(sql`${table.stripeCustomerId} is not null`),
    check(
      "billing_accounts_mode_check",
      sql`${table.mode} in ('prepaid', 'invoiced')`,
    ),
    check(
      "billing_accounts_auto_top_up_check",
      sql`not ${table.autoTopUpEnabled} or (${table.mode} = 'prepaid' and ${table.stripeCustomerId} is not null and ${table.stripePaymentMethodId} is not null and ${table.autoTopUpThreshold} >= 0 and ${table.autoTopUpAmount} > 0)`,
    ),
  ],
);

export const models = pgTable(
  "models",
  {
    id: text("id").primaryKey(),
    aliases: text("aliases")
      .array()
      .notNull()
      .default(sql`'{}'::text[]`),
    name: text("name").notNull(),
    status: text("status", { enum: MODEL_STATUSES }).notNull(),
    properties: jsonb("properties").$type<ModelProperties>().notNull(),
    // The exact OpenRouter model that serves this one when our deployments cannot.
    openrouterModelId: text("openrouter_model_id"),
    // The Hugging Face tokenizer, at an immutable revision, that counts tokens
    // when no deployment supplies one.
    tokenizerPath: text("tokenizer_path"),
    tokenizerRevision: text("tokenizer_revision"),
    // Only this organization's API keys can call the model, and only it sees it
    // listed. Null is the public catalog.
    organizationId: uuid("organization_id").references(() => organizations.id, {
      onDelete: "restrict",
    }),
    // The interface the model serves, declared by its catalog definition;
    // every deployment's release must serve it.
    // The default only keeps workers from before this column writing their
    // catalog during a rolling upgrade; every definition declares its type.
    type: text("type", { enum: MODEL_TYPES }).notNull().default("chat"),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
  },
  (table) => [
    index("models_organization_id_idx")
      .on(table.organizationId)
      .where(sql`${table.organizationId} is not null`),
    check("models_type_check", sql`${table.type} in ('chat', 'decision')`),
    // `<owner slug>/<name>`: one segment after the slug, so an owned name can
    // never be a private model version (`<slug>/<task>/<version>`). Aliases
    // contain no comma.
    check(
      "models_owned_name_check",
      sql`${table.organizationId} is null or (${table.id} ~ '^[^/]+/[^/]+$' and ${table.id} = lower(${table.id}) and array_to_string(${table.aliases}, ',') !~ '(^|,)[^,/]*/[^,/]*/')`,
    ),
    check(
      "models_openrouter_model_id_check",
      sql`${table.openrouterModelId} ~ '^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$' and char_length(${table.openrouterModelId}) <= 200`,
    ),
    check(
      "models_tokenizer_check",
      sql`(${table.tokenizerPath} is null and ${table.tokenizerRevision} is null) or (${table.tokenizerPath} is not null and ${table.tokenizerRevision} is not null and char_length(${table.tokenizerPath}) between 1 and 300 and ${table.tokenizerRevision} ~ '^[0-9a-f]{40}$')`,
    ),
    check(
      "models_id_length_check",
      sql`char_length(${table.id}) between 1 and 200`,
    ),
    check(
      "models_name_length_check",
      sql`char_length(${table.name}) between 1 and 200`,
    ),
    check(
      "models_status_check",
      sql`${table.status} in ('available', 'unavailable', 'retired')`,
    ),
  ],
);

export const modelDeployments = pgTable(
  "model_deployments",
  {
    id: uuid("id").primaryKey(),
    instanceId: uuid("instance_id").references(() => instances.id, {
      onDelete: "restrict",
    }),
    modelId: text("model_id")
      .notNull()
      .references(() => models.id, { onDelete: "restrict" }),
    status: text("status", { enum: DEPLOYMENT_STATUSES }).notNull(),
    provider: text("provider").notNull(),
    region: text("region").notNull(),
    faultDomain: text("fault_domain").notNull(),
    serviceUrl: text("service_url").notNull(),
    release: jsonb("release").$type<ModelDeploymentRelease>().notNull(),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
  },
  (table) => [
    index("model_deployments_model_status_index").on(
      table.modelId,
      table.status,
      table.id,
    ),
    check(
      "model_deployments_status_check",
      sql`${table.status} in ('available', 'unavailable', 'draining')`,
    ),
    check(
      "model_deployments_service_url_length_check",
      sql`char_length(${table.serviceUrl}) between 1 and 2048`,
    ),
    check(
      "model_deployments_service_url_scheme_check",
      sql`${table.serviceUrl} ~ '^https?://'`,
    ),
    check(
      "model_deployments_provider_check",
      sql`${table.provider} ~ '^[a-z][a-z0-9_-]{0,99}$'`,
    ),
    check(
      "model_deployments_region_length_check",
      sql`char_length(${table.region}) between 1 and 100`,
    ),
    check(
      "model_deployments_fault_domain_length_check",
      sql`char_length(${table.faultDomain}) between 1 and 300`,
    ),
  ],
);

export const balanceTransactions = pgTable(
  "balance_transactions",
  {
    id: uuid("id").primaryKey(),
    organizationId: uuid("organization_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    type: text("type", { enum: BALANCE_TRANSACTION_TYPES }).notNull(),
    amount: bigint("amount", { mode: "bigint" }).notNull(),
    balanceAfter: bigint("balance_after", { mode: "bigint" }).notNull(),
    sourceType: text("source_type", { enum: BALANCE_SOURCE_TYPES }).notNull(),
    sourceId: text("source_id").notNull(),
    periodStart: timestamp("period_start", {
      withTimezone: true,
      mode: "date",
    }),
    periodEnd: timestamp("period_end", {
      withTimezone: true,
      mode: "date",
    }),
    generationCount: bigint("generation_count", { mode: "bigint" }),
    createdBy: uuid("created_by").references(() => users.id, {
      onDelete: "restrict",
    }),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
  },
  (table) => [
    unique("balance_transactions_source_unique").on(
      table.sourceType,
      table.sourceId,
    ),
    index("balance_transactions_organization_created_at_index").on(
      table.organizationId,
      table.createdAt,
      table.id,
    ),
    check(
      "balance_transactions_type_check",
      sql`${table.type} in ('topup', 'usage', 'refund', 'chargeback', 'credit', 'payment', 'adjustment')`,
    ),
    check(
      "balance_transactions_source_type_check",
      sql`${table.sourceType} in ('stripe_checkout_session', 'stripe_refund', 'stripe_dispute', 'generation_settlement_batch', 'openrouter_payment', 'operator', 'stripe_invoice')`,
    ),
    check(
      "balance_transactions_amount_nonzero_check",
      sql`${table.amount} <> 0`,
    ),
    check(
      "balance_transactions_period_check",
      sql`(${table.periodStart} is null and ${table.periodEnd} is null) or (${table.periodStart} is not null and ${table.periodEnd} > ${table.periodStart})`,
    ),
    check(
      "balance_transactions_generation_count_check",
      sql`${table.generationCount} is null or ${table.generationCount} > 0`,
    ),
  ],
);

export const topUpCharges = pgTable(
  "top_up_charges",
  {
    id: uuid("id").primaryKey(),
    organizationId: uuid("organization_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    reason: text("reason", { enum: TOP_UP_CHARGE_REASONS }).notNull(),
    status: text("status", { enum: TOP_UP_CHARGE_STATUSES }).notNull(),
    amount: bigint("amount", { mode: "bigint" }).notNull(),
    stripeCustomerId: text("stripe_customer_id").notNull(),
    stripePaymentMethodId: text("stripe_payment_method_id").notNull(),
    stripeInvoiceId: text("stripe_invoice_id"),
    failure: text("failure"),
    requestKey: text("request_key"),
    createdBy: uuid("created_by").references(() => users.id, {
      onDelete: "set null",
    }),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
    updatedAt: timestamp("updated_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
  },
  (table) => [
    uniqueIndex("top_up_charges_one_pending_per_organization")
      .on(table.organizationId)
      .where(sql`${table.status} = 'pending'`),
    uniqueIndex("top_up_charges_stripe_invoice_id_unique")
      .on(table.stripeInvoiceId)
      .where(sql`${table.stripeInvoiceId} is not null`),
    uniqueIndex("top_up_charges_organization_request_key_unique")
      .on(table.organizationId, table.requestKey)
      .where(sql`${table.requestKey} is not null`),
    index("top_up_charges_organization_created_at_index").on(
      table.organizationId,
      table.createdAt,
    ),
    check(
      "top_up_charges_reason_check",
      sql`${table.reason} in ('top_up', 'auto_top_up')`,
    ),
    check(
      "top_up_charges_status_check",
      sql`${table.status} in ('pending', 'succeeded', 'failed')`,
    ),
    check("top_up_charges_amount_check", sql`${table.amount} > 0`),
  ],
);

// The first method and amount of each keyed top-up request, so a retry repeats
// that attempt whichever method it asks for.
export const topUpRequests = pgTable(
  "top_up_requests",
  {
    organizationId: uuid("organization_id")
      .notNull()
      .references(() => organizations.id, { onDelete: "cascade" }),
    requestKey: text("request_key").notNull(),
    method: text("method", { enum: TOP_UP_METHODS }).notNull(),
    amount: bigint("amount", { mode: "bigint" }).notNull(),
    // A retried Checkout must resend Stripe the first request's parameters.
    requestedBy: uuid("requested_by").references(() => users.id, {
      onDelete: "set null",
    }),
    replacesPaymentMethodId: text("replaces_payment_method_id"),
    createdAt: timestamp("created_at", { withTimezone: true, mode: "date" })
      .defaultNow()
      .notNull(),
  },
  (table) => [
    primaryKey({ columns: [table.organizationId, table.requestKey] }),
    check(
      "top_up_requests_method_check",
      sql`${table.method} in ('card', 'checkout')`,
    ),
    check("top_up_requests_amount_check", sql`${table.amount} > 0`),
  ],
);
