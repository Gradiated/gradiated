-- Fail fast instead of queueing the gateway's reads of tasks behind a lock wait.
SET LOCAL lock_timeout = '5s';--> statement-breakpoint
ALTER TABLE "task_versions" ADD COLUMN "expires_at" timestamp with time zone;--> statement-breakpoint
ALTER TABLE "tasks" ADD COLUMN "purpose" text DEFAULT 'serving' NOT NULL;--> statement-breakpoint
CREATE INDEX "task_versions_expires_index" ON "task_versions" USING btree ("expires_at") WHERE "task_versions"."expires_at" is not null;--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_purpose_check" CHECK ("tasks"."purpose" in ('serving', 'eval') and ("tasks"."purpose" = 'serving' or "tasks"."production_version_id" is null));