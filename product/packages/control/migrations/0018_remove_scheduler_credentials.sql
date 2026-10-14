ALTER TABLE "instances" DROP CONSTRAINT "instances_serving_url_check";--> statement-breakpoint
ALTER TABLE "model_deployments" DROP CONSTRAINT "model_deployments_orchestrator_check";--> statement-breakpoint
DROP INDEX "instances_nomad_node_unique";--> statement-breakpoint
ALTER TABLE "instances" DROP COLUMN "nomad_node_id";--> statement-breakpoint
ALTER TABLE "instances" DROP COLUMN "serving_url";--> statement-breakpoint
ALTER TABLE "instances" DROP COLUMN "certificate";--> statement-breakpoint
ALTER TABLE "model_deployments" DROP COLUMN "orchestrator";