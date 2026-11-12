ALTER TABLE "organizations" ADD COLUMN "slug" text DEFAULT left(md5(gen_random_uuid()::text), 16) NOT NULL;--> statement-breakpoint
-- Existing organizations get a slug from their name, in creation order. New ones
-- start with the random default and choose theirs during onboarding.
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
    WHILE EXISTS (SELECT 1 FROM organizations WHERE slug = candidate AND id <> organization.id) LOOP
      ordinal := ordinal + 1;
      candidate := base || '-' || ordinal;
    END LOOP;
    UPDATE organizations SET slug = candidate WHERE id = organization.id;
  END LOOP;
END $$;--> statement-breakpoint
ALTER TABLE "organizations" ADD CONSTRAINT "organizations_slug_unique" UNIQUE("slug");--> statement-breakpoint
ALTER TABLE "organizations" ADD CONSTRAINT "organizations_slug_check" CHECK ("organizations"."slug" ~ '^[a-z0-9][a-z0-9-]{0,37}[a-z0-9]$');--> statement-breakpoint
ALTER TABLE "tasks" ADD COLUMN "organization_id" uuid;--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_organization_workspace_fk" FOREIGN KEY ("organization_id","workspace_id") REFERENCES "public"."workspaces"("organization_id","id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_model_name_check" CHECK ("tasks"."organization_id" is null or (strpos("tasks"."name", '/') = 0 and char_length("tasks"."name") <= 128));--> statement-breakpoint
ALTER TABLE "tasks" ADD CONSTRAINT "tasks_organization_name_unique" UNIQUE("organization_id","name");--> statement-breakpoint
-- A task's name becomes its model name when its first version is written, from
-- any code version. Names that can't be model names stay unclaimed. Taking the organization lock serializes this with slug
-- changes, which lock that row first; callers already hold the task row.
CREATE FUNCTION claim_model_name() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM 1 FROM organizations
  JOIN workspaces ON workspaces.organization_id = organizations.id
  WHERE workspaces.id = NEW.workspace_id
  FOR UPDATE OF organizations;
  UPDATE tasks SET organization_id = workspaces.organization_id
  FROM workspaces
  WHERE tasks.id = NEW.task_id
    AND tasks.organization_id IS NULL
    AND strpos(tasks.name, '/') = 0
    AND char_length(tasks.name) <= 128
    AND workspaces.id = tasks.workspace_id;
  RETURN NEW;
END $$;--> statement-breakpoint
CREATE TRIGGER task_versions_claim_model_name AFTER INSERT ON task_versions FOR EACH ROW EXECUTE FUNCTION claim_model_name();--> statement-breakpoint
-- Tasks with versions claim their names now. Where one name has versions in
-- several workspaces of an organization, the oldest task keeps it.
UPDATE "tasks" SET "organization_id" = "claimed"."organization_id"
FROM (
  SELECT DISTINCT ON ("workspaces"."organization_id", "tasks"."name") "tasks"."id", "workspaces"."organization_id"
  FROM "tasks"
  JOIN "workspaces" ON "workspaces"."id" = "tasks"."workspace_id"
  WHERE strpos("tasks"."name", '/') = 0
    AND char_length("tasks"."name") <= 128
    AND EXISTS (SELECT 1 FROM "task_versions" WHERE "task_versions"."task_id" = "tasks"."id")
  ORDER BY "workspaces"."organization_id", "tasks"."name", "tasks"."created_at", "tasks"."id"
) "claimed"
WHERE "tasks"."id" = "claimed"."id";--> statement-breakpoint
-- Tasks left unclaimed can't be called, so they stop advertising a production model.
UPDATE "tasks" SET "production_version_id" = NULL
WHERE "organization_id" IS NULL AND "production_version_id" IS NOT NULL;--> statement-breakpoint
ALTER TABLE "task_versions" DROP CONSTRAINT "task_versions_workspace_name_unique";--> statement-breakpoint
-- Trained versions named `<task>-<yyyymmdd>[-n]` become `<yyyy-mm-dd>[-n]` within
-- their task, unless another version of the task already has that name.
UPDATE "task_versions" SET "name" = "renamed"."name"
FROM (
  SELECT "task_versions"."id", "task_versions"."task_id", regexp_replace(substr("task_versions"."name", length("tasks"."name") + 2), '^([0-9]{4})([0-9]{2})([0-9]{2})', '\1-\2-\3') AS "name"
  FROM "task_versions"
  JOIN "tasks" ON "tasks"."id" = "task_versions"."task_id"
  WHERE "task_versions"."training_run_id" IS NOT NULL
    AND left("task_versions"."name", length("tasks"."name") + 1) = "tasks"."name" || '-'
    AND substr("task_versions"."name", length("tasks"."name") + 2) ~ '^[0-9]{8}(-[0-9]+)?$'
) "renamed"
WHERE "task_versions"."id" = "renamed"."id"
  AND NOT EXISTS (SELECT 1 FROM "task_versions" "taken" WHERE "taken"."task_id" = "renamed"."task_id" AND "taken"."name" = "renamed"."name");--> statement-breakpoint
ALTER TABLE "task_versions" ADD CONSTRAINT "task_versions_task_name_unique" UNIQUE("task_id","name");
