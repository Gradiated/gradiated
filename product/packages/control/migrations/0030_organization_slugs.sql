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
ALTER TABLE "tasks" ADD COLUMN "organization_id" uuid;--> statement-breakpoint
UPDATE "tasks" SET "organization_id" = "workspaces"."organization_id" FROM "workspaces" WHERE "workspaces"."id" = "tasks"."workspace_id";--> statement-breakpoint
ALTER TABLE "tasks" ALTER COLUMN "organization_id" SET NOT NULL;--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_organization_workspace_fk" FOREIGN KEY ("organization_id","workspace_id") REFERENCES "public"."workspaces"("organization_id","id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
-- Fails if an organization has one task name in two workspaces; rename one first.
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_organization_name_unique" UNIQUE("organization_id","name");--> statement-breakpoint
ALTER TABLE "task_versions" DROP CONSTRAINT "task_versions_workspace_name_unique";--> statement-breakpoint
-- Trained versions named `<task>-<yyyymmdd>[-n]` become `<yyyy-mm-dd>[-n]` within their task.
UPDATE "task_versions" SET "name" = regexp_replace(substr("task_versions"."name", length("tasks"."name") + 2), '^([0-9]{4})([0-9]{2})([0-9]{2})', '\1-\2-\3')
FROM "tasks"
WHERE "tasks"."id" = "task_versions"."task_id"
  AND "task_versions"."training_run_id" IS NOT NULL
  AND left("task_versions"."name", length("tasks"."name") + 1) = "tasks"."name" || '-'
  AND substr("task_versions"."name", length("tasks"."name") + 2) ~ '^[0-9]{8}(-[0-9]+)?$';--> statement-breakpoint
ALTER TABLE "task_versions" ADD CONSTRAINT "task_versions_task_name_unique" UNIQUE("task_id","name");--> statement-breakpoint
-- NOT VALID: trace-registered task names with `/` or over 128 characters may already exist.
ALTER TABLE "task_versions" ADD CONSTRAINT "task_versions_name_segment_check" CHECK (strpos("task_versions"."name", '/') = 0 and char_length("task_versions"."name") <= 128) NOT VALID;--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_name_segment_check" CHECK (strpos("tasks"."name", '/') = 0 and char_length("tasks"."name") <= 128) NOT VALID;
