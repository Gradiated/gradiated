-- PLACEHOLDER PRICES. These are made up, scaled by model size from grad's
-- catalog defaults, and are not final pricing. The version says so with
-- placeholder = true; replace it with a new version, never by editing this one.
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
  ('pv_training_2026_11_27_placeholder', 'train:baai/bge-small-en-v1.5', 'token', 80000000);
