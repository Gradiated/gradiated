-- Fail fast instead of queueing writers of organizations and workspaces behind
-- a lock wait; CREATE TRIGGER does not block their readers.
SET LOCAL lock_timeout = '5s';--> statement-breakpoint
CREATE TABLE "grad_workspace_state_outbox" (
	"workspace_id" uuid PRIMARY KEY NOT NULL,
	"state" text NOT NULL,
	"generation" integer DEFAULT 1 NOT NULL,
	"attempts" integer DEFAULT 0 NOT NULL,
	"last_error" text,
	"next_attempt_at" timestamp with time zone DEFAULT now() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "grad_workspace_state_outbox_state_check" CHECK ("grad_workspace_state_outbox"."state" in ('active', 'suspended', 'deleted'))
);
--> statement-breakpoint
-- One row per workspace holds the newest state; nothing replaces 'deleted'.
-- next_attempt_at is left alone so an in-flight send keeps its claim.
CREATE FUNCTION queue_grad_workspace_state(workspace uuid, desired text) RETURNS void LANGUAGE sql AS $$
  INSERT INTO grad_workspace_state_outbox AS outbox (workspace_id, state)
  VALUES (workspace, desired)
  ON CONFLICT (workspace_id) DO UPDATE
  SET state = excluded.state, generation = outbox.generation + 1, updated_at = now()
  WHERE outbox.state <> 'deleted' AND outbox.state <> excluded.state
$$;
--> statement-breakpoint
CREATE FUNCTION queue_grad_workspace_state_of_workspace() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    PERFORM queue_grad_workspace_state(OLD.id, 'deleted');
    RETURN OLD;
  END IF;
  PERFORM queue_grad_workspace_state(
    NEW.id,
    CASE
      WHEN NEW.archived_at IS NULL AND EXISTS (
        SELECT 1 FROM organizations
        WHERE organizations.id = NEW.organization_id AND organizations.status = 'active'
      ) THEN 'active'
      ELSE 'suspended'
    END
  );
  RETURN NEW;
END $$;
--> statement-breakpoint
CREATE FUNCTION queue_grad_workspace_states_of_organization() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM queue_grad_workspace_state(
    workspaces.id,
    CASE WHEN NEW.status = 'active' THEN 'active' ELSE 'suspended' END
  )
  FROM workspaces
  WHERE workspaces.organization_id = NEW.id AND workspaces.archived_at IS NULL;
  RETURN NEW;
END $$;
--> statement-breakpoint
CREATE TRIGGER workspaces_grad_state_on_archive
AFTER UPDATE OF archived_at ON workspaces
FOR EACH ROW WHEN (OLD.archived_at IS DISTINCT FROM NEW.archived_at)
EXECUTE FUNCTION queue_grad_workspace_state_of_workspace();
--> statement-breakpoint
CREATE TRIGGER workspaces_grad_state_on_delete
AFTER DELETE ON workspaces
FOR EACH ROW EXECUTE FUNCTION queue_grad_workspace_state_of_workspace();
--> statement-breakpoint
CREATE TRIGGER organizations_grad_state_on_status
AFTER UPDATE OF status ON organizations
FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION queue_grad_workspace_states_of_organization();
