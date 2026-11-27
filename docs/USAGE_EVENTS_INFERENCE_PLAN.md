# Inference usage on `usage_events`

- status: plan; not started
- related: [DATA_MODEL.md](DATA_MODEL.md) (`balance_transactions`, `generations`, `usage_events`)

Training usage is written to ClickHouse `usage_events` from day one: grad pushes priced events to the API's training listener, which posts `usage_event` balance transactions and then inserts the events. Inference still bills from `generations`: the gateway prices each generation, the worker ingests `GenerationSettled` into `generations`, and the settlement loop posts one `generation_settlement_batch` per organization and slot. This plan moves inference usage reporting onto `usage_events` so usage views, invoices and Metabase read one table for both products. The money path does not change.

## Why it is not a one-line dual write

- **Price versions.** Every `usage_events` row names a `price_version`. Inference prices are captured per generation as `pricing.components[].unit_price` at admission, and no versioned inference price list exists. Either inference catalog prices become `price_lists` versions (product `inference`, SKUs `inference:<model>:<unit>`), with the gateway stamping the version it admitted with, or inference rows carry a sentinel such as `gateway:pricing:v1` and the unit price as a tag. The first is the real fix; the second only unblocks reporting.
- **One row per component.** A generation has up to six priced components (`request`, `input_token`, `cached_input_token`, `cache_write_token`, `output_token`, `reasoning_token`). That is six `usage_events` rows per generation, so at current volume the table grows several times faster than `generations`.
- **Readers.** The usage summary, the generation log, the console usage page and the Metabase models all read `generations` with its materialized columns. Each needs a `usage_events` query and a reconciliation period.

## Steps

1. **Dual write in the worker.**
   - `generation-ingestion-loop.ts` already inserts each settled generation with an ID-based dedup token before acknowledging the stream entry. It also inserts that generation's nonzero pricing components into `usage_events`:
     - `event_id = inference:gen:<generation_id>:<unit>`
     - `product = inference`
     - `sku = inference:<model_id>:<unit>`
     - `quantity` and `amount_nano_usd` from the component
     - `subject_id = <generation_id>`
     - tags: `api_key_id`, `service_tier`, `status`, and `lane` and `eval_id` once the gateway tags eval traffic.
   - Both inserts happen before the acknowledgement, so a crash replays both. `ReplacingMergeTree` collapses the replay.
2. **Inference price versions.** Pick between the two price-version options above, then add `product = inference` to `price_lists`. The gateway itself keeps pricing from its own catalog snapshot.
3. **Backfill** `usage_events` from `generations` for the retention window with one `INSERT … SELECT` per month partition, using the same derivation as step 1.
4. **Reconcile.** A daily job compares, per organization and day, `sum(amount_nano_usd)` of inference `usage_events` with `generation_settlement_batch` amounts in `balance_transactions`, and alerts on any difference. Run it for a month.
5. **Move the readers.**
   - Move the usage summary (`packages/control/src/usage/service.ts`), the console usage page, Metabase and invoices to `usage_events`, grouped by `product`, so training and inference appear together.
   - The generation log stays on `generations`, which keeps per-request detail.
6. **Settlement stays.** The gateway's Valkey balance, settlement slots and `generation_settlement_batch` postings are unchanged. Nothing bills from `usage_events`; it is the record of what was billed.

## Not double-counting evals

grad's eval jobs call the gateway with eval-lane credentials, so their model and judge tokens are ordinary generations. They are billed by settlement and recorded in step 1 as `product = inference` with `lane = eval`. grad never pushes them: the training listener accepts only `product = training` events with `train:` SKUs.
