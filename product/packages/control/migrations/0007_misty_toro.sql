ALTER TABLE "workspaces" ADD COLUMN "trace_capture_enabled" boolean DEFAULT false NOT NULL;--> statement-breakpoint
ALTER TABLE "workspaces" ADD COLUMN "trace_retention_days" smallint DEFAULT 30 NOT NULL;--> statement-breakpoint
ALTER TABLE "workspaces" ADD CONSTRAINT "workspaces_trace_retention_days_check" CHECK ("workspaces"."trace_retention_days" in (30, 90, 180));