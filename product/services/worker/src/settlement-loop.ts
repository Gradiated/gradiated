import {
  BalanceSourceConflictError,
  SettlementFinancialConflictError,
  type GenerationSettlementReader,
  type GenerationSettlementStore,
  type OrganizationSettlement,
  type SettlementLeadership,
} from "@gradiated/control";

import { WorkerInvariantError } from "./errors.js";
import { serviceLog } from "./logging.js";
import {
  stopwatch,
  type SettlementPassSummary,
  type WorkerMetrics,
} from "./metrics.js";
import {
  lastSlotEndingBy,
  nextSlot,
  parseSlot,
  slotContaining,
  type SettlementSlot,
} from "./settlement-slot.js";
import { sleep } from "./sleep.js";

export type IngestionBoundary = () => Promise<number | null>;

export type SettlementConfig = {
  maxSlotsPerPass: number;
  pollMilliseconds: number;
  settlementDelayMilliseconds: number;
};

export type SettlementTelemetry = Pick<
  WorkerMetrics,
  "setSettlementLeadership" | "recordSettlementPass" | "recordPass"
>;

export type SettlementPass = {
  reader: GenerationSettlementReader;
  leadership: SettlementLeadership;
  ingestionBoundary: IngestionBoundary;
  config: SettlementConfig;
  now: Date;
  cursor: SettlementSlot | null;
  signal?: AbortSignal;
};

export type SettlementPassResult = SettlementPassSummary & {
  cursor: SettlementSlot | null;
};

export type SettlementLoop = {
  reader: GenerationSettlementReader;
  store: GenerationSettlementStore;
  ingestionBoundary: IngestionBoundary;
  config: SettlementConfig;
  telemetry: SettlementTelemetry;
  onReady: () => Promise<void>;
  signal: AbortSignal;
};

export const upperEligibleSlot = (
  now: Date,
  ingestionBoundaryMilliseconds: number,
  settlementDelayMilliseconds: number,
): SettlementSlot | null =>
  lastSlotEndingBy(
    Math.min(
      ingestionBoundaryMilliseconds,
      now.getTime() - settlementDelayMilliseconds,
    ),
  );

const isAtOrBefore = (slot: SettlementSlot, upper: SettlementSlot): boolean =>
  slot.start.getTime() <= upper.start.getTime();

const eligibleBacklogAgeSeconds = (
  cursor: SettlementSlot | null,
  upper: SettlementSlot,
  { now, config }: SettlementPass,
): number => {
  if (!cursor || !isAtOrBefore(cursor, upper)) return 0;

  const overdueMilliseconds =
    now.getTime() - cursor.end.getTime() - config.settlementDelayMilliseconds;

  return Math.max(0, overdueMilliseconds / 1_000);
};

const firstUnsettledSlot = async (
  { reader, leadership }: SettlementPass,
  upper: SettlementSlot,
): Promise<SettlementSlot | null> => {
  const latestPeriodStart = await leadership.getLatestSettlementPeriodStart();
  if (latestPeriodStart) return slotContaining(latestPeriodStart.getTime());

  const earliestSlotId = await reader.getEarliestSlot(upper.id);

  return earliestSlotId ? parseSlot(earliestSlotId) : null;
};

const isChargeable = (settlement: OrganizationSettlement): boolean =>
  settlement.totalCharge > 0n;

const organizationIds = (settlements: readonly OrganizationSettlement[]) =>
  settlements.map((settlement) => settlement.organizationId);

const readSlotSettlements = async (
  reader: GenerationSettlementReader,
  slot: SettlementSlot,
): Promise<OrganizationSettlement[]> => {
  try {
    return await reader.getOrganizationSettlements(slot.id);
  } catch (error) {
    if (!(error instanceof SettlementFinancialConflictError)) throw error;

    throw new WorkerInvariantError(
      "EGENERATION_FINANCIAL_CONFLICT",
      `A generation has conflicting financial values in slot ${slot.id}`,
      { cause: error },
    );
  }
};

const validateSlotShape = (
  slot: SettlementSlot,
  settlements: readonly OrganizationSettlement[],
): void => {
  if (settlements.some((settlement) => settlement.slotId !== slot.id)) {
    throw new WorkerInvariantError(
      "ESLOT_MISMATCH",
      `ClickHouse returned a different settlement slot for ${slot.id}`,
    );
  }

  const allOrganizationIds = organizationIds(settlements);
  if (new Set(allOrganizationIds).size !== allOrganizationIds.length) {
    throw new WorkerInvariantError(
      "EDUPLICATE_ORGANIZATION",
      `ClickHouse returned duplicate organizations for ${slot.id}`,
    );
  }
};

const validateChargeable = (
  slot: SettlementSlot,
  chargeable: readonly OrganizationSettlement[],
  knownOrganizations: ReadonlySet<string>,
): void => {
  for (const settlement of chargeable) {
    if (settlement.generationCount === 0n) {
      throw new WorkerInvariantError(
        "ECHARGE_WITHOUT_GENERATIONS",
        `Chargeable settlement has no generations in slot ${slot.id}`,
      );
    }

    if (!knownOrganizations.has(settlement.organizationId)) {
      throw new WorkerInvariantError(
        "EMISSING_BILLING_ACCOUNT",
        `Billing account is missing for a chargeable organization in slot ${slot.id}`,
      );
    }
  }
};

const postSettlement = async (
  leadership: SettlementLeadership,
  slot: SettlementSlot,
  settlement: OrganizationSettlement,
): Promise<void> => {
  try {
    await leadership.postSettlement({
      generationCount: settlement.generationCount,
      organizationId: settlement.organizationId,
      periodEnd: slot.end,
      periodStart: slot.start,
      slotId: slot.id,
      totalCharge: settlement.totalCharge,
    });
  } catch (error) {
    if (!(error instanceof BalanceSourceConflictError)) throw error;

    throw new WorkerInvariantError(
      "ESETTLEMENT_CONFLICT",
      `A posted settlement differs from ClickHouse in slot ${slot.id}`,
      { cause: error },
    );
  }
};

const settleSlot = async (
  { reader, leadership }: SettlementPass,
  slot: SettlementSlot,
): Promise<void> => {
  const settlements = await readSlotSettlements(reader, slot);

  validateSlotShape(slot, settlements);

  const chargeable = settlements.filter(isChargeable);
  const knownOrganizations = await leadership.getBillingOrganizationIds(
    organizationIds(chargeable),
  );

  validateChargeable(slot, chargeable, knownOrganizations);

  for (const settlement of chargeable) {
    await postSettlement(leadership, slot, settlement);
  }
};

export const processSettlementPass = async (
  pass: SettlementPass,
): Promise<SettlementPassResult> => {
  const idle = {
    cursor: pass.cursor,
    processedSlots: 0,
    eligibleBacklogAgeSeconds: 0,
  };
  const boundary = await pass.ingestionBoundary();
  if (boundary === null) return idle;

  const upper = upperEligibleSlot(
    pass.now,
    boundary,
    pass.config.settlementDelayMilliseconds,
  );
  if (!upper) return idle;

  let cursor = pass.cursor ?? (await firstUnsettledSlot(pass, upper));
  let processedSlots = 0;

  while (
    !pass.signal?.aborted &&
    cursor &&
    isAtOrBefore(cursor, upper) &&
    processedSlots < pass.config.maxSlotsPerPass
  ) {
    await settleSlot(pass, cursor);
    processedSlots += 1;
    cursor = nextSlot(cursor);
  }

  return {
    cursor,
    processedSlots,
    eligibleBacklogAgeSeconds: eligibleBacklogAgeSeconds(cursor, upper, pass),
  };
};

const leadSettlement = async (
  {
    reader,
    ingestionBoundary,
    config,
    telemetry,
    onReady,
    signal,
  }: SettlementLoop,
  leadership: SettlementLeadership,
): Promise<void> => {
  telemetry.setSettlementLeadership(true);
  await onReady();

  let cursor: SettlementSlot | null = null;

  while (!signal.aborted) {
    const elapsedSeconds = stopwatch();
    const result = await processSettlementPass({
      reader,
      leadership,
      ingestionBoundary,
      config,
      now: new Date(),
      cursor,
      signal,
    });

    cursor = result.cursor;
    telemetry.recordSettlementPass(result);
    telemetry.recordPass("settlement", elapsedSeconds());
    await sleep(config.pollMilliseconds, signal);
  }
};

const releaseAfterFailure = async (
  leadership: SettlementLeadership,
): Promise<void> => {
  try {
    await leadership.release();
  } catch (error) {
    serviceLog("error", "settlement_release_failed", {
      loop: "settlement",
      dependency: "postgres",
      error,
    });
  }
};

export const runGenerationSettlementLoop = async (
  loop: SettlementLoop,
): Promise<void> => {
  const { store, config, telemetry, onReady, signal } = loop;

  while (!signal.aborted) {
    const leadership = await store.tryAcquireLeadership();
    if (!leadership) {
      telemetry.setSettlementLeadership(false);
      await onReady();
      await sleep(config.pollMilliseconds, signal);
      continue;
    }

    try {
      await leadSettlement(loop, leadership);
    } catch (error) {
      telemetry.setSettlementLeadership(false);
      await releaseAfterFailure(leadership);
      throw error;
    }

    telemetry.setSettlementLeadership(false);
    await leadership.release();
  }
};
