CREATE TABLE "task_promotions" (
	"id" uuid PRIMARY KEY NOT NULL,
	"task_id" uuid NOT NULL,
	"workspace_id" uuid NOT NULL,
	"previous_version_id" uuid,
	"version_id" uuid NOT NULL,
	"actor_id" uuid,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "version_hostings" (
	"version_id" uuid PRIMARY KEY NOT NULL,
	"desired" text NOT NULL,
	"revision" integer DEFAULT 1 NOT NULL,
	"profile" jsonb NOT NULL,
	"stage" text NOT NULL,
	"error_code" text,
	"requested_by" uuid,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "version_hostings_desired_check" CHECK ("version_hostings"."desired" in ('hosted', 'unhosted')),
	CONSTRAINT "version_hostings_stage_check" CHECK ("version_hostings"."stage" in ('pending', 'ready', 'failed', 'draining', 'unhosted')),
	CONSTRAINT "version_hostings_revision_check" CHECK ("version_hostings"."revision" > 0),
	CONSTRAINT "version_hostings_error_check" CHECK ("version_hostings"."error_code" in ('preparation_failed', 'capacity_unavailable'))
);
--> statement-breakpoint
ALTER TABLE "task_promotions" ADD CONSTRAINT "task_promotions_actor_id_users_id_fk" FOREIGN KEY ("actor_id") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "task_promotions" ADD CONSTRAINT "task_promotions_task_id_workspace_id_tasks_id_workspace_id_fk" FOREIGN KEY ("task_id","workspace_id") REFERENCES "public"."tasks"("id","workspace_id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "task_promotions" ADD CONSTRAINT "task_promotions_version_id_task_id_workspace_id_task_versions_id_task_id_workspace_id_fk" FOREIGN KEY ("version_id","task_id","workspace_id") REFERENCES "public"."task_versions"("id","task_id","workspace_id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "version_hostings" ADD CONSTRAINT "version_hostings_version_id_task_versions_id_fk" FOREIGN KEY ("version_id") REFERENCES "public"."task_versions"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "version_hostings" ADD CONSTRAINT "version_hostings_requested_by_users_id_fk" FOREIGN KEY ("requested_by") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "task_versions" ADD CONSTRAINT "task_versions_id_task_workspace_unique" UNIQUE("id","task_id","workspace_id");