import {
  NANO_USD_PER_USD,
  type BalanceCheck,
  type BalanceCheckResult,
  type UsageEvent,
  type UsageEventRejectionCode,
} from "@gradiated/contracts";
import type { UsageEventWriter } from "../clickhouse/usage-event-ingestion.js";
import type { ControlDatabase } from "../db/client.js";
import { ControlServiceError } from "../errors.js";
import { readBillingAccount } from "./accounts.js";
import {
  BalanceSourceConflictError,
  postBalanceTransaction,
} from "./ledger.js";
import { readCustomerWorkspaceOwners } from "./store.js";
import {
  amountForQuantity,
  readCurrentPriceList,
  readPriceList,
  type PriceListProduct,
  type PriceListRecord,
} from "./price-lists.js";

export class UsageEventRejectedError extends Error {
  constructor(
    readonly code: UsageEventRejectionCode,
    readonly eventId: string,
    message: string,
  ) {
    super(message);
    this.name = "UsageEventRejectedError";
  }
}

export interface UsageEventIngestResult {
  accepted: number;
  duplicates: number;
}

export interface TrainingBillingService {
  ingestUsageEvents(events: UsageEvent[]): Promise<UsageEventIngestResult>;
  checkBalance(input: BalanceCheck): Promise<BalanceCheckResult>;
  priceList(input: {
    product: PriceListProduct;
    priceVersion?: string | undefined;
  }): Promise<PriceListRecord>;
}

const estimateNanoUsd = (input: BalanceCheck): bigint =>
  input.estimated_amount_nano_usd ??
  BigInt(Math.ceil((input.estimated_cost_usd ?? 0) * Number(NANO_USD_PER_USD)));

export const createTrainingBillingService = (
  database: ControlDatabase,
  usageEvents: UsageEventWriter,
  now: () => Date = () => new Date(),
): TrainingBillingService => {
  const priceLists = new Map<string, PriceListRecord>();

  // Versions are immutable, so one read per version and process is enough.
  const priceListVersion = async (id: string) => {
    const cached = priceLists.get(id);
    if (cached) return cached;

    const list = await readPriceList(database, id);
    if (list) priceLists.set(id, list);

    return list;
  };

  const priceEvent = async (event: UsageEvent) => {
    const list = await priceListVersion(event.price_version);
    // inference: SKUs are eval estimates; the gateway bills that usage.
    const item =
      list?.product === event.product && event.sku.startsWith("train:")
        ? list.items.find((candidate) => candidate.sku === event.sku)
        : undefined;
    if (!item)
      throw new UsageEventRejectedError(
        "price_mismatch",
        event.event_id,
        `Price version ${event.price_version} has no price for ${event.sku}.`,
      );

    const amount = amountForQuantity(
      BigInt(event.quantity),
      item.priceNanoUsdPerMillion,
    );
    if (amount !== event.amount_nano_usd)
      throw new UsageEventRejectedError(
        "price_mismatch",
        event.event_id,
        `The amount for ${event.quantity} ${item.unit}s at ${event.price_version} is ${amount} nano-USD, not ${event.amount_nano_usd}.`,
      );

    return amount;
  };

  return {
    async ingestUsageEvents(events) {
      const owners = await readCustomerWorkspaceOwners(database, [
        ...new Set(events.map((event) => event.workspace_id)),
      ]);

      const priced = [];
      for (const event of events) {
        const owner = owners.get(event.workspace_id);
        if (!owner)
          throw new UsageEventRejectedError(
            "unknown_workspace",
            event.event_id,
            `Workspace ${event.workspace_id} is not a customer workspace.`,
          );

        priced.push({ event, owner, amount: await priceEvent(event) });
      }

      // One lock order across concurrent batches keeps postings deadlock-free.
      const postings = [...priced].sort((a, b) =>
        a.owner.organizationId.localeCompare(b.owner.organizationId),
      );

      let duplicates = 0;
      await database.transaction(async (transaction) => {
        for (const { event, owner, amount } of postings) {
          if (amount === 0n) continue;

          const posting = await postBalanceTransaction(transaction, {
            organizationId: owner.organizationId,
            type: "usage",
            amount: -amount,
            sourceType: "usage_event",
            sourceId: event.event_id,
            createdBy: null,
          }).catch((error: unknown) => {
            if (error instanceof BalanceSourceConflictError)
              throw new UsageEventRejectedError(
                "event_conflict",
                event.event_id,
                `Event ${event.event_id} was already billed with different values.`,
              );
            throw error;
          });
          if (posting.replayed) duplicates += 1;
        }
      });

      // The ledger commits first; a failed insert is retried with the same events.
      await usageEvents.insert(
        priced.map(({ event, owner, amount }) => ({
          eventId: event.event_id,
          organizationId: owner.organizationId,
          workspaceId: event.workspace_id,
          product: event.product,
          sku: event.sku,
          quantity: BigInt(event.quantity),
          amountNanoUsd: amount,
          priceVersion: event.price_version,
          occurredAt: new Date(event.occurred_at),
          subjectId: event.subject_id,
          tags: event.tags,
        })),
      );

      return { accepted: events.length - duplicates, duplicates };
    },

    async checkBalance(input) {
      const owner = (
        await readCustomerWorkspaceOwners(database, [input.workspace_id])
      ).get(input.workspace_id);
      if (!owner)
        throw new ControlServiceError(
          "not_found",
          "The workspace does not exist.",
        );

      if (owner.organizationStatus !== "active" || owner.archivedAt)
        return { allowed: false, reason: "suspended" };

      const account = await readBillingAccount(database, owner.organizationId);
      if (account.mode === "invoiced") return { allowed: true };

      return account.balance >= estimateNanoUsd(input)
        ? { allowed: true }
        : { allowed: false, reason: "insufficient_balance" };
    },

    async priceList({ product, priceVersion }) {
      const list = priceVersion
        ? await priceListVersion(priceVersion)
        : await readCurrentPriceList(database, product, now());
      if (!list || list.product !== product)
        throw new ControlServiceError(
          "not_found",
          priceVersion
            ? `Price version ${priceVersion} does not exist.`
            : `No ${product} price list is in effect.`,
        );

      return list;
    },
  };
};
