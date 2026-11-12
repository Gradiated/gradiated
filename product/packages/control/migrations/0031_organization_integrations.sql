CREATE TABLE "integrations" (
	"id" uuid PRIMARY KEY NOT NULL,
	"organization_id" uuid NOT NULL,
	"provider" text NOT NULL,
	"external_id" text NOT NULL,
	"status" text NOT NULL,
	"settings" jsonb NOT NULL,
	"created_by" uuid NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "integrations_provider_check" CHECK ("integrations"."provider" in ('github', 'slack')),
	CONSTRAINT "integrations_status_check" CHECK ("integrations"."status" in ('pending', 'active', 'revoked'))
);
--> statement-breakpoint
ALTER TABLE "organizations" ADD COLUMN "metadata" jsonb DEFAULT '{"schema_version":1}'::jsonb NOT NULL;--> statement-breakpoint
ALTER TABLE "integrations" ADD CONSTRAINT "integrations_organization_id_organizations_id_fk" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "integrations" ADD CONSTRAINT "integrations_created_by_users_id_fk" FOREIGN KEY ("created_by") REFERENCES "public"."users"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "integrations_provider_external_id_unique" ON "integrations" USING btree ("provider","external_id") WHERE "integrations"."status" <> 'revoked';--> statement-breakpoint
CREATE UNIQUE INDEX "integrations_organization_slack_unique" ON "integrations" USING btree ("organization_id") WHERE "integrations"."provider" = 'slack' and "integrations"."status" <> 'revoked';--> statement-breakpoint
CREATE INDEX "integrations_organization_id_index" ON "integrations" USING btree ("organization_id");