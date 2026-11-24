ALTER TABLE "models" ADD COLUMN "organization_id" uuid;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "type" text;--> statement-breakpoint
-- Every model declares its interface. Existing rows take the type their Git
-- catalog definition declares: the three SystemOne models are decision models,
-- every other model chat. Deployment history plays no part.
UPDATE "models" SET "type" = CASE
  WHEN "id" IN ('jaredpalmer/kev-9b', 'perplexity-ai/pplx-decider-v1.2', 'gradiated/linden-1')
  THEN 'decision' ELSE 'chat' END;--> statement-breakpoint
ALTER TABLE "models" ALTER COLUMN "type" SET NOT NULL;--> statement-breakpoint
-- Workers still running the previous release upsert their catalog without a
-- type during the rollout; they only rewrite existing rows, which keep theirs.
ALTER TABLE "models" ALTER COLUMN "type" SET DEFAULT 'chat';--> statement-breakpoint
ALTER TABLE "models" ADD CONSTRAINT "models_organization_id_organizations_id_fk" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "models_organization_id_idx" ON "models" USING btree ("organization_id") WHERE "models"."organization_id" is not null;--> statement-breakpoint
ALTER TABLE "models" ADD CONSTRAINT "models_type_check" CHECK ("models"."type" in ('chat', 'decision'));--> statement-breakpoint
ALTER TABLE "models" ADD CONSTRAINT "models_owned_name_check" CHECK ("models"."organization_id" is null or ("models"."id" ~ '^[^/]+/[^/]+$' and "models"."id" = lower("models"."id") and array_to_string("models"."aliases", ',') !~ '(^|,)[^,/]*/[^,/]*/'));--> statement-breakpoint
-- A name the organization's own hosted model already answers to stays
-- unclaimed, so a training run admitted before that model existed can't make
-- both ambiguous. The gateway looks hosted IDs up in lowercase.
CREATE OR REPLACE FUNCTION claim_model_name() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM 1 FROM organizations
  JOIN workspaces ON workspaces.organization_id = organizations.id
  WHERE workspaces.id = NEW.workspace_id
  FOR UPDATE OF organizations;
  UPDATE tasks SET organization_id = workspaces.organization_id
  FROM workspaces
  JOIN organizations ON organizations.id = workspaces.organization_id
  WHERE tasks.id = NEW.task_id
    AND tasks.organization_id IS NULL
    AND strpos(tasks.name, '/') = 0
    AND char_length(tasks.name) <= 128
    AND workspaces.id = tasks.workspace_id
    AND NOT EXISTS (
      SELECT 1 FROM models
      WHERE models.organization_id = organizations.id
        AND models.status <> 'retired'
        AND (models.id = organizations.slug || '/' || lower(tasks.name)
          OR organizations.slug || '/' || lower(tasks.name) = ANY (models.aliases))
    );
  RETURN NEW;
END $$;