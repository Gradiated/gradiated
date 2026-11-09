CREATE TABLE "model_uploads" (
	"id" uuid PRIMARY KEY NOT NULL,
	"workspace_id" uuid NOT NULL,
	"input" jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"version_id" uuid
);
--> statement-breakpoint
ALTER TABLE "task_versions" ALTER COLUMN "training_run_id" DROP NOT NULL;--> statement-breakpoint
ALTER TABLE "model_uploads" ADD CONSTRAINT "model_uploads_workspace_id_workspaces_id_fk" FOREIGN KEY ("workspace_id") REFERENCES "public"."workspaces"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "model_uploads" ADD CONSTRAINT "model_uploads_version_id_task_versions_id_fk" FOREIGN KEY ("version_id") REFERENCES "public"."task_versions"("id") ON DELETE set null ON UPDATE no action;