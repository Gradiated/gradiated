CREATE TABLE "top_up_charges" (
	"id" uuid PRIMARY KEY NOT NULL,
	"organization_id" uuid NOT NULL,
	"reason" text NOT NULL,
	"status" text NOT NULL,
	"amount" bigint NOT NULL,
	"stripe_customer_id" text NOT NULL,
	"stripe_payment_method_id" text NOT NULL,
	"stripe_invoice_id" text,
	"failure" text,
	"request_key" text,
	"created_by" uuid,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "top_up_charges_reason_check" CHECK ("top_up_charges"."reason" in ('top_up', 'auto_top_up')),
	CONSTRAINT "top_up_charges_status_check" CHECK ("top_up_charges"."status" in ('pending', 'succeeded', 'failed')),
	CONSTRAINT "top_up_charges_amount_check" CHECK ("top_up_charges"."amount" > 0)
);
--> statement-breakpoint
CREATE TABLE "top_up_requests" (
	"organization_id" uuid NOT NULL,
	"request_key" text NOT NULL,
	"method" text NOT NULL,
	"amount" bigint NOT NULL,
	"requested_by" uuid,
	"replaces_payment_method_id" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "top_up_requests_organization_id_request_key_pk" PRIMARY KEY("organization_id","request_key"),
	CONSTRAINT "top_up_requests_method_check" CHECK ("top_up_requests"."method" in ('card', 'checkout')),
	CONSTRAINT "top_up_requests_amount_check" CHECK ("top_up_requests"."amount" > 0)
);
--> statement-breakpoint
ALTER TABLE "balance_transactions" DROP CONSTRAINT "balance_transactions_source_type_check";--> statement-breakpoint
ALTER TABLE "billing_accounts" ADD COLUMN "stripe_payment_method_id" text;--> statement-breakpoint
ALTER TABLE "billing_accounts" ADD COLUMN "auto_top_up_enabled" boolean DEFAULT false NOT NULL;--> statement-breakpoint
ALTER TABLE "billing_accounts" ADD COLUMN "auto_top_up_threshold" bigint;--> statement-breakpoint
ALTER TABLE "billing_accounts" ADD COLUMN "auto_top_up_amount" bigint;--> statement-breakpoint
ALTER TABLE "billing_accounts" ADD COLUMN "auto_top_up_updated_at" timestamp with time zone;--> statement-breakpoint
ALTER TABLE "top_up_charges" ADD CONSTRAINT "top_up_charges_organization_id_organizations_id_fk" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "top_up_charges" ADD CONSTRAINT "top_up_charges_created_by_users_id_fk" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "top_up_requests" ADD CONSTRAINT "top_up_requests_organization_id_organizations_id_fk" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "top_up_requests" ADD CONSTRAINT "top_up_requests_requested_by_users_id_fk" FOREIGN KEY ("requested_by") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "top_up_charges_one_pending_per_organization" ON "top_up_charges" USING btree ("organization_id") WHERE "top_up_charges"."status" = 'pending';--> statement-breakpoint
CREATE UNIQUE INDEX "top_up_charges_stripe_invoice_id_unique" ON "top_up_charges" USING btree ("stripe_invoice_id") WHERE "top_up_charges"."stripe_invoice_id" is not null;--> statement-breakpoint
CREATE UNIQUE INDEX "top_up_charges_organization_request_key_unique" ON "top_up_charges" USING btree ("organization_id","request_key") WHERE "top_up_charges"."request_key" is not null;--> statement-breakpoint
CREATE INDEX "top_up_charges_organization_created_at_index" ON "top_up_charges" USING btree ("organization_id","created_at");--> statement-breakpoint
ALTER TABLE "balance_transactions" ADD CONSTRAINT "balance_transactions_source_type_check" CHECK ("balance_transactions"."source_type" in ('stripe_checkout_session', 'stripe_refund', 'stripe_dispute', 'generation_settlement_batch', 'openrouter_payment', 'operator', 'stripe_invoice'));--> statement-breakpoint
ALTER TABLE "billing_accounts" ADD CONSTRAINT "billing_accounts_auto_top_up_check" CHECK (not "billing_accounts"."auto_top_up_enabled" or ("billing_accounts"."mode" = 'prepaid' and "billing_accounts"."stripe_customer_id" is not null and "billing_accounts"."stripe_payment_method_id" is not null and "billing_accounts"."auto_top_up_threshold" >= 0 and "billing_accounts"."auto_top_up_amount" > 0));