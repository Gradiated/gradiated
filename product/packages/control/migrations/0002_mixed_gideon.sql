CREATE TABLE "balance_transactions" (
	"id" uuid PRIMARY KEY NOT NULL,
	"organization_id" uuid NOT NULL,
	"type" text NOT NULL,
	"amount" bigint NOT NULL,
	"balance_after" bigint NOT NULL,
	"source_type" text NOT NULL,
	"source_id" text NOT NULL,
	"period_start" timestamp with time zone,
	"period_end" timestamp with time zone,
	"generation_count" bigint,
	"created_by" uuid,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "balance_transactions_source_unique" UNIQUE("source_type","source_id"),
	CONSTRAINT "balance_transactions_type_check" CHECK ("balance_transactions"."type" in ('topup', 'usage', 'refund', 'chargeback', 'credit', 'payment', 'adjustment')),
	CONSTRAINT "balance_transactions_source_type_check" CHECK ("balance_transactions"."source_type" in ('stripe_checkout_session', 'stripe_refund', 'stripe_dispute', 'generation_settlement_batch', 'openrouter_payment', 'operator')),
	CONSTRAINT "balance_transactions_amount_nonzero_check" CHECK ("balance_transactions"."amount" <> 0),
	CONSTRAINT "balance_transactions_period_check" CHECK (("balance_transactions"."period_start" is null and "balance_transactions"."period_end" is null) or ("balance_transactions"."period_start" is not null and "balance_transactions"."period_end" > "balance_transactions"."period_start")),
	CONSTRAINT "balance_transactions_generation_count_check" CHECK ("balance_transactions"."generation_count" is null or "balance_transactions"."generation_count" > 0)
);
--> statement-breakpoint
CREATE TABLE "models" (
	"id" text PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"status" text NOT NULL,
	"properties" jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "models_id_length_check" CHECK (char_length("models"."id") between 1 and 200),
	CONSTRAINT "models_name_length_check" CHECK (char_length("models"."name") between 1 and 200),
	CONSTRAINT "models_status_check" CHECK ("models"."status" in ('available', 'unavailable', 'retired'))
);
--> statement-breakpoint
ALTER TABLE "balance_transactions" ADD CONSTRAINT "balance_transactions_organization_id_organizations_id_fk" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "balance_transactions" ADD CONSTRAINT "balance_transactions_created_by_users_id_fk" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "balance_transactions_organization_created_at_index" ON "balance_transactions" USING btree ("organization_id","created_at","id");