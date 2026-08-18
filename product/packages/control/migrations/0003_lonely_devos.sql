CREATE TABLE "model_deployments" (
	"id" uuid PRIMARY KEY NOT NULL,
	"model_id" text NOT NULL,
	"status" text NOT NULL,
	"service_url" text NOT NULL,
	"release" jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "model_deployments_status_check" CHECK ("model_deployments"."status" in ('available', 'unavailable', 'draining')),
	CONSTRAINT "model_deployments_service_url_length_check" CHECK (char_length("model_deployments"."service_url") between 1 and 2048),
	CONSTRAINT "model_deployments_service_url_scheme_check" CHECK ("model_deployments"."service_url" ~ '^https?://')
);
--> statement-breakpoint
ALTER TABLE "model_deployments" ADD CONSTRAINT "model_deployments_model_id_models_id_fk" FOREIGN KEY ("model_id") REFERENCES "public"."models"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "model_deployments_model_status_index" ON "model_deployments" USING btree ("model_id","status","id");