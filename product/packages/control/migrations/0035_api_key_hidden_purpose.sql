CREATE UNIQUE INDEX "api_keys_hidden_owner_name_unique" ON "api_keys" USING btree ("workspace_id","created_by","name") WHERE "api_keys"."hidden";--> statement-breakpoint
DROP INDEX "api_keys_hidden_owner_unique";
