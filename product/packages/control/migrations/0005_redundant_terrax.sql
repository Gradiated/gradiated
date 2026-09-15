CREATE TABLE "instances" (
	"id" uuid PRIMARY KEY NOT NULL,
	"provider" text NOT NULL,
	"provider_account_id" text NOT NULL,
	"provider_instance_id" text NOT NULL,
	"region" text,
	"fault_domain" text,
	"sku" text NOT NULL,
	"nomad_node_id" uuid,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"retired_at" timestamp with time zone,
	CONSTRAINT "instances_identity_check" CHECK (length("instances"."provider") between 1 and 100 and length("instances"."provider_account_id") between 1 and 200 and length("instances"."provider_instance_id") between 1 and 200),
	CONSTRAINT "instances_sku_check" CHECK (length("instances"."sku") between 1 and 200)
);
--> statement-breakpoint
ALTER TABLE "model_deployments" ADD COLUMN "instance_id" uuid;--> statement-breakpoint
CREATE UNIQUE INDEX "instances_provider_identity_unique" ON "instances" USING btree ("provider","provider_account_id","provider_instance_id");--> statement-breakpoint
CREATE UNIQUE INDEX "instances_nomad_node_unique" ON "instances" USING btree ("nomad_node_id");--> statement-breakpoint
ALTER TABLE "model_deployments" ADD CONSTRAINT "model_deployments_instance_id_instances_id_fk" FOREIGN KEY ("instance_id") REFERENCES "public"."instances"("id") ON DELETE restrict ON UPDATE no action;