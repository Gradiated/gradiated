CREATE TABLE "task_versions" (
	"id" uuid PRIMARY KEY NOT NULL,
	"workspace_id" uuid NOT NULL,
	"task_id" uuid NOT NULL,
	"training_run_id" uuid NOT NULL,
	"name" text NOT NULL,
	"base_model_id" text NOT NULL,
	"adapter" jsonb NOT NULL,
	"status" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "task_versions_training_run_id_unique" UNIQUE("training_run_id"),
	CONSTRAINT "task_versions_workspace_name_unique" UNIQUE("workspace_id","name"),
	CONSTRAINT "task_versions_status_check" CHECK ("task_versions"."status" in ('available', 'unavailable'))
);
--> statement-breakpoint
CREATE TABLE "tasks" (
	"id" uuid PRIMARY KEY NOT NULL,
	"workspace_id" uuid NOT NULL,
	"name" text NOT NULL,
	"base_model_id" text,
	"comparison_model_id" text,
	"production_version_id" uuid,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "tasks_workspace_name_unique" UNIQUE("workspace_id","name")
);
--> statement-breakpoint
CREATE TABLE "training_run_events" (
	"id" bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY (sequence name "training_run_events_id_seq" INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1),
	"run_id" uuid NOT NULL,
	"at" timestamp with time zone NOT NULL,
	"source" text NOT NULL,
	"attempt" integer NOT NULL,
	"payload" jsonb NOT NULL,
	CONSTRAINT "training_run_events_source_check" CHECK ("training_run_events"."source" ~ '^[a-z][a-z0-9_-]{0,63}$')
);
--> statement-breakpoint
CREATE TABLE "training_runs" (
	"id" uuid PRIMARY KEY NOT NULL,
	"task_id" uuid NOT NULL,
	"trigger" text NOT NULL,
	"requested_by" uuid,
	"stage" text NOT NULL,
	"base_model_id" text NOT NULL,
	"input_cutoff" timestamp with time zone NOT NULL,
	"dataset" jsonb,
	"evaluation" jsonb,
	"cancel_requested_at" timestamp with time zone,
	"finished_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "training_runs_trigger_check" CHECK ("training_runs"."trigger" in ('automation', 'manual')),
	CONSTRAINT "training_runs_stage_check" CHECK ("training_runs"."stage" in ('queued', 'building_dataset', 'awaiting_capacity', 'training', 'verifying', 'publishing', 'evaluating', 'cancelling', 'succeeded', 'failed', 'cancelled'))
);
--> statement-breakpoint
ALTER TABLE "workspaces" ADD COLUMN "evaluation_judge" text DEFAULT 'openai/gpt-5.6-sol' NOT NULL;--> statement-breakpoint
ALTER TABLE "task_versions" ADD CONSTRAINT "task_versions_workspace_id_workspaces_id_fk" FOREIGN KEY ("workspace_id") REFERENCES "public"."workspaces"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "task_versions" ADD CONSTRAINT "task_versions_task_id_tasks_id_fk" FOREIGN KEY ("task_id") REFERENCES "public"."tasks"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "task_versions" ADD CONSTRAINT "task_versions_training_run_id_training_runs_id_fk" FOREIGN KEY ("training_run_id") REFERENCES "public"."training_runs"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "task_versions" ADD CONSTRAINT "task_versions_base_model_id_models_id_fk" FOREIGN KEY ("base_model_id") REFERENCES "public"."models"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_workspace_id_workspaces_id_fk" FOREIGN KEY ("workspace_id") REFERENCES "public"."workspaces"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_base_model_id_models_id_fk" FOREIGN KEY ("base_model_id") REFERENCES "public"."models"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_production_version_id_task_versions_id_fk" FOREIGN KEY ("production_version_id") REFERENCES "public"."task_versions"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "training_run_events" ADD CONSTRAINT "training_run_events_run_id_training_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "public"."training_runs"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "training_runs" ADD CONSTRAINT "training_runs_task_id_tasks_id_fk" FOREIGN KEY ("task_id") REFERENCES "public"."tasks"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "training_runs" ADD CONSTRAINT "training_runs_requested_by_users_id_fk" FOREIGN KEY ("requested_by") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "training_runs" ADD CONSTRAINT "training_runs_base_model_id_models_id_fk" FOREIGN KEY ("base_model_id") REFERENCES "public"."models"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "task_versions_task_created_index" ON "task_versions" USING btree ("task_id","created_at");--> statement-breakpoint
CREATE INDEX "training_run_events_run_index" ON "training_run_events" USING btree ("run_id","id");--> statement-breakpoint
CREATE UNIQUE INDEX "training_runs_one_active_per_task" ON "training_runs" USING btree ("task_id") WHERE "training_runs"."finished_at" is null;--> statement-breakpoint
CREATE INDEX "training_runs_task_created_index" ON "training_runs" USING btree ("task_id","created_at");--> statement-breakpoint
ALTER TABLE "workspaces" ADD CONSTRAINT "workspaces_evaluation_judge_check" CHECK ("workspaces"."evaluation_judge" in ('Qwen/Qwen3-0.6B', 'openai/gpt-6-astra', 'openai/gpt-6-sol', 'openai/gpt-6-luna', 'openai/gpt-5.6-sol', 'openai/gpt-5', 'anthropic/claude-fable-5-1', 'anthropic/claude-opus-5-5', 'anthropic/claude-sonnet-5-5', 'anthropic/claude-opus-5', 'anthropic/claude-sonnet-5'));
--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_id_workspace_unique" UNIQUE("id","workspace_id");
--> statement-breakpoint
ALTER TABLE "training_runs" ADD CONSTRAINT "training_runs_id_task_unique" UNIQUE("id","task_id");
--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_name_routable_check" CHECK ("tasks"."name" not in ('.', '..'));
--> statement-breakpoint
ALTER TABLE "task_versions" ADD CONSTRAINT "task_versions_task_workspace_fk" FOREIGN KEY ("task_id","workspace_id") REFERENCES "public"."tasks"("id","workspace_id") ON DELETE cascade ON UPDATE no action;
--> statement-breakpoint
ALTER TABLE "task_versions" ADD CONSTRAINT "task_versions_run_task_fk" FOREIGN KEY ("training_run_id","task_id") REFERENCES "public"."training_runs"("id","task_id") ON DELETE cascade ON UPDATE no action;
