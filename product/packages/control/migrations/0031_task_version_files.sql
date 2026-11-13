CREATE TABLE "task_version_files" (
	"id" uuid PRIMARY KEY NOT NULL,
	"workspace_id" uuid NOT NULL,
	"version_id" uuid NOT NULL,
	"name" text NOT NULL,
	"content_type" text NOT NULL,
	"size_bytes" bigint NOT NULL,
	"status" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"completed_at" timestamp with time zone,
	CONSTRAINT "task_version_files_status_check" CHECK ("task_version_files"."status" in ('pending', 'ready', 'deleted'))
);
--> statement-breakpoint
ALTER TABLE "task_version_files" ADD CONSTRAINT "task_version_files_workspace_id_workspaces_id_fk" FOREIGN KEY ("workspace_id") REFERENCES "public"."workspaces"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "task_version_files" ADD CONSTRAINT "task_version_files_version_id_task_versions_id_fk" FOREIGN KEY ("version_id") REFERENCES "public"."task_versions"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "task_version_files_ready_name_unique" ON "task_version_files" USING btree ("version_id","name") WHERE "task_version_files"."status" = 'ready';--> statement-breakpoint
CREATE INDEX "task_version_files_version_index" ON "task_version_files" USING btree ("version_id");