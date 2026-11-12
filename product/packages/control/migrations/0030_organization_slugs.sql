CREATE TABLE "organization_slugs" (
	"slug" text PRIMARY KEY NOT NULL,
	"organization_id" uuid NOT NULL,
	"is_current" boolean NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "organization_slugs_slug_check" CHECK ("organization_slugs"."slug" ~ '^[a-z0-9][a-z0-9-]{0,37}[a-z0-9]$')
);
--> statement-breakpoint
ALTER TABLE "organization_slugs" ADD CONSTRAINT "organization_slugs_organization_id_organizations_id_fk" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "organization_slugs_one_current" ON "organization_slugs" USING btree ("organization_id") WHERE "organization_slugs"."is_current";--> statement-breakpoint
-- Same rules as availableOrganizationSlug, applied in creation order.
DO $$
DECLARE
  organization record;
  base text;
  candidate text;
  ordinal integer;
BEGIN
  FOR organization IN SELECT id, name FROM organizations ORDER BY created_at, id LOOP
    base := trim(both '-' from left(trim(both '-' from regexp_replace(lower(organization.name), '[^a-z0-9]+', '-', 'g')), 30));
    IF length(base) < 2
      OR base = ANY (ARRAY['admin', 'anthropic', 'api', 'billing', 'console', 'docs', 'gradiated', 'help', 'internal', 'models', 'openai', 'settings', 'staff', 'support', 'system', 'v1', 'www'])
      OR EXISTS (SELECT 1 FROM models WHERE lower(split_part(models.id, '/', 1)) = base)
    THEN
      base := trim(both '-' from base || '-org');
    END IF;
    candidate := base;
    ordinal := 1;
    WHILE EXISTS (SELECT 1 FROM organization_slugs WHERE slug = candidate) LOOP
      ordinal := ordinal + 1;
      candidate := base || '-' || ordinal;
    END LOOP;
    INSERT INTO organization_slugs (slug, organization_id, is_current) VALUES (candidate, organization.id, true);
  END LOOP;
END $$;--> statement-breakpoint
ALTER TABLE "tasks" ADD COLUMN "model_organization_id" uuid;--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_model_organization_workspace_fk" FOREIGN KEY ("model_organization_id","workspace_id") REFERENCES "public"."workspaces"("organization_id","id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_model_name_check" CHECK ("tasks"."model_organization_id" is null or (strpos("tasks"."name", '/') = 0 and char_length("tasks"."name") <= 128));--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_model_name_unique" UNIQUE("model_organization_id","name");--> statement-breakpoint
-- Tasks that have trained or uploaded already claim their names. Where one name
-- is a model in several workspaces of an organization, the oldest keeps it.
UPDATE "tasks" SET "model_organization_id" = "claimed"."organization_id"
FROM (
  SELECT DISTINCT ON ("workspaces"."organization_id", "tasks"."name") "tasks"."id", "workspaces"."organization_id"
  FROM "tasks"
  JOIN "workspaces" ON "workspaces"."id" = "tasks"."workspace_id"
  WHERE strpos("tasks"."name", '/') = 0
    AND char_length("tasks"."name") <= 128
    AND (EXISTS (SELECT 1 FROM "task_versions" WHERE "task_versions"."task_id" = "tasks"."id")
      OR EXISTS (SELECT 1 FROM "training_runs" WHERE "training_runs"."task_id" = "tasks"."id"))
  ORDER BY "workspaces"."organization_id", "tasks"."name", "tasks"."created_at", "tasks"."id"
) "claimed"
WHERE "tasks"."id" = "claimed"."id";--> statement-breakpoint
ALTER TABLE "task_versions" DROP CONSTRAINT "task_versions_workspace_name_unique";--> statement-breakpoint
-- Trained versions named `<task>-<yyyymmdd>[-n]` become `<yyyy-mm-dd>[-n]` within their task.
UPDATE "task_versions" SET "name" = regexp_replace(substr("task_versions"."name", length("tasks"."name") + 2), '^([0-9]{4})([0-9]{2})([0-9]{2})', '\1-\2-\3')
FROM "tasks"
WHERE "tasks"."id" = "task_versions"."task_id"
  AND "task_versions"."training_run_id" IS NOT NULL
  AND left("task_versions"."name", length("tasks"."name") + 1) = "tasks"."name" || '-'
  AND substr("task_versions"."name", length("tasks"."name") + 2) ~ '^[0-9]{8}(-[0-9]+)?$';--> statement-breakpoint
ALTER TABLE "task_versions" ADD CONSTRAINT "task_versions_task_name_unique" UNIQUE("task_id","name");
