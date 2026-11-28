-- PLACEHOLDER PRICES. Every price here is made up and is not final pricing.
-- train: SKUs are scaled by model size from grad's catalog defaults; inference:
-- SKUs, for served models only, are blended prompt+completion prices grad uses
-- only to estimate evals and to allow judges (the gateway bills eval inference
-- itself). The version says so with placeholder = true; replace it with a new
-- version, never by editing this one.
INSERT INTO "price_lists" ("id", "product", "effective_at", "placeholder")
VALUES ('pv_training_2026_11_27_placeholder', 'training', '2026-11-27T00:00:00Z', true);
--> statement-breakpoint
INSERT INTO "price_list_items" ("price_list_id", "sku", "unit", "price_nano_usd_per_million")
VALUES
  ('pv_training_2026_11_27_placeholder', 'train:qwen/qwen3-0.6b', 'token', 150000000),
  ('pv_training_2026_11_27_placeholder', 'train:qwen/qwen3-1.7b', 'token', 220000000),
  ('pv_training_2026_11_27_placeholder', 'train:qwen/qwen3-4b', 'token', 300000000),
  ('pv_training_2026_11_27_placeholder', 'train:qwen/qwen3-8b', 'token', 400000000),
  ('pv_training_2026_11_27_placeholder', 'train:qwen/qwen3-14b', 'token', 700000000),
  ('pv_training_2026_11_27_placeholder', 'train:qwen/qwen3-32b', 'token', 1200000000),
  ('pv_training_2026_11_27_placeholder', 'train:gradiated/linden-1', 'token', 200000000),
  ('pv_training_2026_11_27_placeholder', 'train:baai/bge-small-en-v1.5', 'token', 80000000),
  ('pv_training_2026_11_27_placeholder', 'inference:qwen/qwen3-0.6b', 'token', 50000000),
  ('pv_training_2026_11_27_placeholder', 'inference:gradiated/linden-1', 'token', 200000000),
  ('pv_training_2026_11_27_placeholder', 'inference:moonshotai/kimi-k3.1-pro', 'token', 1500000000),
  ('pv_training_2026_11_27_placeholder', 'inference:deepseek/deepseek-v4.1-flash', 'token', 400000000),
  ('pv_training_2026_11_27_placeholder', 'inference:deepseek/deepseek-v4.1-flash-1017', 'token', 400000000),
  ('pv_training_2026_11_27_placeholder', 'inference:z-ai/glm-5.3-flash', 'token', 500000000),
  ('pv_training_2026_11_27_placeholder', 'inference:z-ai/glm-5.3', 'token', 1500000000),
  ('pv_training_2026_11_27_placeholder', 'inference:openai/gpt-6.1-sol', 'token', 5000000000),
  ('pv_training_2026_11_27_placeholder', 'inference:openai/gpt-6.1-sol-pro', 'token', 40000000000),
  ('pv_training_2026_11_27_placeholder', 'inference:openai/gpt-6-astra', 'token', 2000000000),
  ('pv_training_2026_11_27_placeholder', 'inference:openai/gpt-6-astra-pro', 'token', 15000000000),
  ('pv_training_2026_11_27_placeholder', 'inference:openai/gpt-6-sol', 'token', 5000000000),
  ('pv_training_2026_11_27_placeholder', 'inference:openai/gpt-6-sol-pro', 'token', 40000000000),
  ('pv_training_2026_11_27_placeholder', 'inference:openai/gpt-6-luna', 'token', 500000000),
  ('pv_training_2026_11_27_placeholder', 'inference:openai/gpt-6-luna-pro', 'token', 4000000000),
  ('pv_training_2026_11_27_placeholder', 'inference:openai/gpt-5.6-sol', 'token', 4000000000),
  ('pv_training_2026_11_27_placeholder', 'inference:openai/gpt-5', 'token', 3000000000),
  ('pv_training_2026_11_27_placeholder', 'inference:anthropic/claude-fable-5-1', 'token', 20000000000),
  ('pv_training_2026_11_27_placeholder', 'inference:anthropic/claude-opus-5-5', 'token', 15000000000),
  ('pv_training_2026_11_27_placeholder', 'inference:anthropic/claude-sonnet-5-5', 'token', 6000000000),
  ('pv_training_2026_11_27_placeholder', 'inference:anthropic/claude-haiku-5-5', 'token', 1500000000),
  ('pv_training_2026_11_27_placeholder', 'inference:anthropic/claude-opus-5', 'token', 15000000000),
  ('pv_training_2026_11_27_placeholder', 'inference:anthropic/claude-sonnet-5', 'token', 6000000000);
