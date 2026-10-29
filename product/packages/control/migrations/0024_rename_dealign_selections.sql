UPDATE "workspaces"
SET "default_judge_model" = 'dealignai/glm-5.3-flash-uncensored', "updated_at" = now()
WHERE "default_judge_model" = 'dealignai/glm-5.3-flash-uncensored-nvfp4';
--> statement-breakpoint
UPDATE "tasks"
SET "judge_model_id" = CASE
      WHEN "judge_model_id" = 'dealignai/glm-5.3-flash-uncensored-nvfp4'
      THEN 'dealignai/glm-5.3-flash-uncensored' ELSE "judge_model_id" END,
    "comparison_model_id" = CASE
      WHEN "comparison_model_id" = 'dealignai/glm-5.3-flash-uncensored-nvfp4'
      THEN 'dealignai/glm-5.3-flash-uncensored' ELSE "comparison_model_id" END,
    "updated_at" = now()
WHERE "judge_model_id" = 'dealignai/glm-5.3-flash-uncensored-nvfp4'
   OR "comparison_model_id" = 'dealignai/glm-5.3-flash-uncensored-nvfp4';
