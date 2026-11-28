-- grad (the training platform) authenticates grad_ keys through this view with
-- the read-only role grad_auth_reader. Columns are only ever added; a breaking
-- change ships auth_principals_v2 next to it. Revoked, expired and hidden keys
-- and keys of non-customer organizations have no row. status is 'active' only
-- while the organization is active, the workspace is not archived and the key's
-- creator is an active member (or verified staff, as in the API's access checks).
CREATE VIEW "auth_principals_v1" WITH (security_barrier = true) AS
SELECT
  "api_keys"."digest" AS "key_hash",
  "api_keys"."id" AS "api_key_id",
  "api_keys"."workspace_id",
  "api_keys"."organization_id" AS "org_id",
  "organizations"."slug" AS "org_slug",
  "api_keys"."created_by" AS "user_id",
  'key:' || "api_keys"."id"::text AS "actor",
  CASE
    WHEN "staff"."id" IS NOT NULL THEN 'admin'
    ELSE coalesce("organization_members"."role", 'member')
  END AS "role",
  CASE
    WHEN "organizations"."status" = 'active'
      AND "workspaces"."archived_at" IS NULL
      AND ("staff"."id" IS NOT NULL OR "organization_members"."status" = 'active')
    THEN 'active'
    ELSE 'suspended'
  END AS "status",
  "api_keys"."scopes",
  "api_keys"."expires_at"
FROM "api_keys"
JOIN "organizations" ON "organizations"."id" = "api_keys"."organization_id"
JOIN "workspaces" ON "workspaces"."id" = "api_keys"."workspace_id"
  AND "workspaces"."organization_id" = "api_keys"."organization_id"
LEFT JOIN "organization_members"
  ON "organization_members"."organization_id" = "api_keys"."organization_id"
  AND "organization_members"."user_id" = "api_keys"."created_by"
LEFT JOIN "users" AS "staff" ON "staff"."id" = "api_keys"."created_by"
  AND "staff"."is_staff" AND "staff"."email_verified"
WHERE "organizations"."kind" = 'customer'
  AND "api_keys"."revoked_at" IS NULL
  AND NOT "api_keys"."hidden"
  AND ("api_keys"."expires_at" IS NULL OR "api_keys"."expires_at" > now());
--> statement-breakpoint
REVOKE ALL ON "auth_principals_v1" FROM PUBLIC;
--> statement-breakpoint
-- The infrastructure bootstrap job creates the login role and grants this
-- too once the view exists, so the grant holds whichever runs first.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grad_auth_reader') THEN
    GRANT SELECT ON "auth_principals_v1" TO grad_auth_reader;
  END IF;
END
$$;
