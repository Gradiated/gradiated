ALTER TABLE "organizations" ADD COLUMN "auto_join_domain" text;--> statement-breakpoint
ALTER TABLE "organizations" ADD COLUMN "onboarded_at" timestamp with time zone;--> statement-breakpoint
CREATE UNIQUE INDEX "organizations_auto_join_domain_unique" ON "organizations" USING btree ("auto_join_domain");--> statement-breakpoint
UPDATE "organizations" SET "onboarded_at" = "created_at";