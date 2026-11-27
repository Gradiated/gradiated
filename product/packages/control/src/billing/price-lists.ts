import { asc, desc, eq, lte, and } from "drizzle-orm";
import { z } from "zod";

import type { ControlDatabase } from "../db/client.js";
import {
  PRICE_LIST_PRODUCTS,
  PRICE_UNITS,
  priceListItems,
  priceLists,
} from "../db/schema/index.js";
import type { LedgerExecutor } from "./ledger.js";

const PriceListItemRecordSchema = z.object({
  sku: z.string().min(1),
  unit: z.enum(PRICE_UNITS),
  priceNanoUsdPerMillion: z.bigint().nonnegative(),
});

const PriceListRecordSchema = z.object({
  id: z.string().min(1),
  product: z.enum(PRICE_LIST_PRODUCTS),
  effectiveAt: z.date(),
  placeholder: z.boolean(),
  items: z.array(PriceListItemRecordSchema),
});

export type PriceListRecord = z.infer<typeof PriceListRecordSchema>;
export type PriceListProduct = PriceListRecord["product"];

const withItems = async (
  executor: ControlDatabase | LedgerExecutor,
  list: typeof priceLists.$inferSelect | undefined,
): Promise<PriceListRecord | undefined> => {
  if (!list) return undefined;

  const items = await executor
    .select({
      sku: priceListItems.sku,
      unit: priceListItems.unit,
      priceNanoUsdPerMillion: priceListItems.priceNanoUsdPerMillion,
    })
    .from(priceListItems)
    .where(eq(priceListItems.priceListId, list.id))
    .orderBy(asc(priceListItems.sku));

  return PriceListRecordSchema.parse({ ...list, items });
};

export const readPriceList = async (
  executor: ControlDatabase | LedgerExecutor,
  id: string,
): Promise<PriceListRecord | undefined> => {
  const [list] = await executor
    .select()
    .from(priceLists)
    .where(eq(priceLists.id, id))
    .limit(1);

  return withItems(executor, list);
};

export const readCurrentPriceList = async (
  executor: ControlDatabase | LedgerExecutor,
  product: PriceListProduct,
  now: Date,
): Promise<PriceListRecord | undefined> => {
  const [list] = await executor
    .select()
    .from(priceLists)
    .where(
      and(eq(priceLists.product, product), lte(priceLists.effectiveAt, now)),
    )
    .orderBy(desc(priceLists.effectiveAt))
    .limit(1);

  return withItems(executor, list);
};

// round_half_up(quantity × price / 10^6), as grad computes it.
export const amountForQuantity = (
  quantity: bigint,
  priceNanoUsdPerMillion: bigint,
): bigint => (quantity * priceNanoUsdPerMillion + 500_000n) / 1_000_000n;
