ALTER TABLE "model_deployments" ADD COLUMN "provider" text;--> statement-breakpoint
ALTER TABLE "model_deployments" ADD COLUMN "region" text;--> statement-breakpoint
ALTER TABLE "model_deployments" ADD COLUMN "fault_domain" text;--> statement-breakpoint
UPDATE "model_deployments" SET "provider" = 'legacy', "region" = 'unknown', "fault_domain" = 'legacy:' || "id"::text;--> statement-breakpoint
ALTER TABLE "model_deployments" ALTER COLUMN "provider" SET NOT NULL;--> statement-breakpoint
ALTER TABLE "model_deployments" ALTER COLUMN "region" SET NOT NULL;--> statement-breakpoint
ALTER TABLE "model_deployments" ALTER COLUMN "fault_domain" SET NOT NULL;--> statement-breakpoint
ALTER TABLE "model_deployments" ADD CONSTRAINT "model_deployments_provider_check" CHECK ("model_deployments"."provider" ~ '^[a-z][a-z0-9_-]{0,99}$');--> statement-breakpoint
ALTER TABLE "model_deployments" ADD CONSTRAINT "model_deployments_region_length_check" CHECK (char_length("model_deployments"."region") between 1 and 100);--> statement-breakpoint
ALTER TABLE "model_deployments" ADD CONSTRAINT "model_deployments_fault_domain_length_check" CHECK (char_length("model_deployments"."fault_domain") between 1 and 300);
