UPDATE "workspaces"
SET "default_judge_model" = 'dealignai/glm-5.3-flash-uncensored', "updated_at" = now()
WHERE "default_judge_model" IN ('dealignai/glm-5.3-flash-uncensored-nvfp4', 'z-ai/glm-5.3-flash');
--> statement-breakpoint
UPDATE "tasks"
SET "judge_model_id" = CASE
      WHEN "judge_model_id" IN ('dealignai/glm-5.3-flash-uncensored-nvfp4', 'z-ai/glm-5.3-flash')
      THEN 'dealignai/glm-5.3-flash-uncensored' ELSE "judge_model_id" END,
    "comparison_model_id" = CASE
      WHEN "comparison_model_id" IN ('dealignai/glm-5.3-flash-uncensored-nvfp4', 'z-ai/glm-5.3-flash')
      THEN 'dealignai/glm-5.3-flash-uncensored' ELSE "comparison_model_id" END,
    "updated_at" = now()
WHERE "judge_model_id" IN ('dealignai/glm-5.3-flash-uncensored-nvfp4', 'z-ai/glm-5.3-flash')
   OR "comparison_model_id" IN ('dealignai/glm-5.3-flash-uncensored-nvfp4', 'z-ai/glm-5.3-flash');
--> statement-breakpoint
UPDATE "task_versions"
SET "status" = 'unavailable', "updated_at" = now()
WHERE "base_model_id" = 'z-ai/glm-5.3-flash' AND "status" = 'available';
--> statement-breakpoint
UPDATE "tasks"
SET "training_schedule" = NULL, "updated_at" = now()
WHERE "base_model_id" = 'z-ai/glm-5.3-flash' AND "training_schedule" IS NOT NULL;
