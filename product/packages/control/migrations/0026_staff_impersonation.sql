ALTER TABLE "sessions" ADD COLUMN "impersonated_by" uuid;
--> statement-breakpoint
ALTER TABLE "sessions" ADD COLUMN "impersonator_session_id" uuid;
--> statement-breakpoint
ALTER TABLE "sessions" ADD CONSTRAINT "sessions_impersonated_by_users_id_fk" FOREIGN KEY ("impersonated_by") REFERENCES "users"("id") ON DELETE CASCADE;
