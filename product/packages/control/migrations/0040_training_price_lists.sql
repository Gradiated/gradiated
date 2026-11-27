CREATE TABLE "price_list_items" (
	"price_list_id" text NOT NULL,
	"sku" text NOT NULL,
	"unit" text NOT NULL,
	"price_nano_usd_per_million" bigint NOT NULL,
	CONSTRAINT "price_list_items_price_list_id_sku_pk" PRIMARY KEY("price_list_id","sku"),
	CONSTRAINT "price_list_items_sku_check" CHECK ("price_list_items"."sku" ~ '^train:[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$'),
	CONSTRAINT "price_list_items_unit_check" CHECK ("price_list_items"."unit" in ('token')),
	CONSTRAINT "price_list_items_price_check" CHECK ("price_list_items"."price_nano_usd_per_million" >= 0)
);
--> statement-breakpoint
CREATE TABLE "price_lists" (
	"id" text PRIMARY KEY NOT NULL,
	"product" text NOT NULL,
	"effective_at" timestamp with time zone NOT NULL,
	"placeholder" boolean NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "price_lists_id_check" CHECK ("price_lists"."id" ~ '^pv_[a-z0-9_]{1,60}$'),
	CONSTRAINT "price_lists_product_check" CHECK ("price_lists"."product" in ('training'))
);
--> statement-breakpoint
ALTER TABLE "balance_transactions" DROP CONSTRAINT "balance_transactions_source_type_check";--> statement-breakpoint
ALTER TABLE "price_list_items" ADD CONSTRAINT "price_list_items_price_list_id_price_lists_id_fk" FOREIGN KEY ("price_list_id") REFERENCES "public"."price_lists"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "price_lists_product_effective_at_unique" ON "price_lists" USING btree ("product","effective_at");--> statement-breakpoint
ALTER TABLE "balance_transactions" ADD CONSTRAINT "balance_transactions_source_type_check" CHECK ("balance_transactions"."source_type" in ('stripe_checkout_session', 'stripe_refund', 'stripe_dispute', 'generation_settlement_batch', 'openrouter_payment', 'operator', 'stripe_invoice', 'usage_event'));