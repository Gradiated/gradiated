CREATE TABLE "invitations" (
	"id" uuid PRIMARY KEY NOT NULL,
	"organization_id" uuid NOT NULL,
	"email" text NOT NULL,
	"role" text NOT NULL,
	"token_digest" "bytea" NOT NULL,
	"expires_at" timestamp with time zone NOT NULL,
	"accepted_at" timestamp with time zone,
	"revoked_at" timestamp with time zone,
	"created_by" uuid NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "invitations_role_check" CHECK ("invitations"."role" in ('admin', 'member')),
	CONSTRAINT "invitations_email_normalized_check" CHECK ("invitations"."email" = lower(btrim("invitations"."email"))),
	CONSTRAINT "invitations_single_outcome_check" CHECK ("invitations"."accepted_at" is null or "invitations"."revoked_at" is null)
);
--> statement-breakpoint
ALTER TABLE "organization_members" DROP CONSTRAINT "organization_members_role_check";--> statement-breakpoint
UPDATE "organization_members" SET "role" = 'admin', "updated_at" = now() WHERE "role" IN ('owner', 'billing');--> statement-breakpoint
-- API pods from before this release still write 'owner' during a rollout or rollback; drop this trigger once none remain.
CREATE FUNCTION "organization_members_legacy_role"() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW."role" IN ('owner', 'billing') THEN
    NEW."role" := 'admin';
  END IF;
  RETURN NEW;
END;
$$;--> statement-breakpoint
CREATE TRIGGER "organization_members_legacy_role" BEFORE INSERT OR UPDATE OF "role" ON "organization_members" FOR EACH ROW EXECUTE FUNCTION "organization_members_legacy_role"();--> statement-breakpoint
ALTER TABLE "invitations" ADD CONSTRAINT "invitations_organization_id_organizations_id_fk" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "invitations" ADD CONSTRAINT "invitations_created_by_users_id_fk" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "invitations_token_digest_unique" ON "invitations" USING btree ("token_digest");--> statement-breakpoint
CREATE UNIQUE INDEX "invitations_pending_email_unique" ON "invitations" USING btree ("organization_id","email") WHERE "invitations"."accepted_at" is null and "invitations"."revoked_at" is null;--> statement-breakpoint
CREATE INDEX "invitations_pending_email_index" ON "invitations" USING btree ("email") WHERE "invitations"."accepted_at" is null and "invitations"."revoked_at" is null;--> statement-breakpoint
ALTER TABLE "organization_members" ADD CONSTRAINT "organization_members_role_check" CHECK ("organization_members"."role" in ('admin', 'member'));