-- Adding a nullable column only changes the catalog, but its ACCESS EXCLUSIVE
-- lock waits behind open transactions on api_keys while every credential lookup
-- (gateway, proxy, API) queues behind it. Fail the migration instead; rerun it.
SET LOCAL lock_timeout = '3s';--> statement-breakpoint
ALTER TABLE "api_keys" ADD COLUMN "scopes" text[];
