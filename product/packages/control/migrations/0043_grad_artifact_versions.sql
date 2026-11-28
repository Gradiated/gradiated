-- Fail fast instead of queueing the gateway's reads behind a lock wait.
SET LOCAL lock_timeout = '5s';--> statement-breakpoint
CREATE TABLE "task_production_changes" (
	"id" uuid PRIMARY KEY NOT NULL,
	"task_id" uuid NOT NULL,
	"from_version_id" uuid,
	"to_version_id" uuid,
	"actor" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "task_production_changes_actor_check" CHECK ("task_production_changes"."actor" ~ '^(user|key|service):[A-Za-z0-9_-]{1,64}$')
);
--> statement-breakpoint
CREATE TABLE "task_version_pin_releases" (
	"version_id" uuid PRIMARY KEY NOT NULL,
	"workspace_id" uuid NOT NULL,
	"artifact_id" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "task_production_changes" ADD CONSTRAINT "task_production_changes_task_id_tasks_id_fk" FOREIGN KEY ("task_id") REFERENCES "public"."tasks"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "task_production_changes" ADD CONSTRAINT "task_production_changes_from_version_id_task_versions_id_fk" FOREIGN KEY ("from_version_id") REFERENCES "public"."task_versions"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "task_production_changes" ADD CONSTRAINT "task_production_changes_to_version_id_task_versions_id_fk" FOREIGN KEY ("to_version_id") REFERENCES "public"."task_versions"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "task_production_changes_task_created_index" ON "task_production_changes" USING btree ("task_id","created_at");--> statement-breakpoint
CREATE UNIQUE INDEX "task_versions_task_artifact_unique" ON "task_versions" USING btree ("task_id",("adapter"->'source'->>'artifact_id')) WHERE "task_versions"."adapter" ? 'source';