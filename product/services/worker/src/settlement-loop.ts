import type {
  GenerationSettlementReader,
  GenerationSettlementStore,
  OrganizationSettlement,
  SettlementLeadership,
} from "@gradiated/control";
import type { RedisClientType } from "@gradiated/valkey";
import { DateTime } from "luxon";

const slotMilliseconds = 300_000;
const slotIdFormat = "yyyyLLdd'T'HHmmss'Z-300s-v1'";
const streamIdPattern = /^(0|[1-9][0-9]*)-(0|[1-9][0-9]*)$/;

export type SettlementLoopOptions = {
  consumerGroup: string;
  maxSlotsPerPass: number;
  onLeadership?: ((isLeader: boolean) => void) | undefined;
  onReady?: (() => Promise<void>) | undefined;
  onPass?:
    | ((result: SettlementPassResult, durationSeconds: number) => void)
    | undefined;
  pollMilliseconds: number;
  settlementDelayMilliseconds: number;
  stream: string;
};

export type SettlementPassResult = {
  nextSlotId: string | null;
  eligibleBacklogAgeSeconds: number;
  processedSlots: number;
};

export const formatSettlementSlotId = (date: Date): string => {
  const milliseconds = date.getTime();
  if (!Number.isSafeInteger(milliseconds)) {
    throw new Error("Settlement slot date is invalid");
  }
  const start = Math.floor(milliseconds / slotMilliseconds) * slotMilliseconds;
  return DateTime.fromMillis(start, { zone: "utc" }).toFormat(slotIdFormat);
};

export const parseSettlementSlotId = (
  slotId: string,
): { end: Date; start: Date } => {
  const start = DateTime.fromFormat(slotId, slotIdFormat, {
    locale: "en",
    setZone: true,
    zone: "utc",
  });
  if (
    !start.isValid ||
    start.toFormat(slotIdFormat) !== slotId ||
    start.second !== 0 ||
    start.minute % 5 !== 0
  ) {
    throw new Error(`Invalid settlement slot ID: ${slotId}`);
  }
  return {
    start: start.toJSDate(),
    end: start.plus({ minutes: 5 }).toJSDate(),
  };
};

const streamMilliseconds = (streamId: string): number => {
  const match = streamIdPattern.exec(streamId);
  if (!match?.[1]) throw new Error(`Invalid Valkey Stream ID: ${streamId}`);
  const milliseconds = Number(match[1]);
  if (!Number.isSafeInteger(milliseconds)) {
    throw new Error(
      `Valkey Stream ID is outside the supported range: ${streamId}`,
    );
  }
  return milliseconds;
};

export const getUpperEligibleSlotId = (
  now: Date,
  ingestionBoundaryMilliseconds: number,
  settlementDelayMilliseconds: number,
): string | null => {
  const boundary = Math.min(
    ingestionBoundaryMilliseconds,
    now.getTime() - settlementDelayMilliseconds,
  );
  const slotEnd = Math.floor(boundary / slotMilliseconds) * slotMilliseconds;
  if (slotEnd < slotMilliseconds) return null;
  return formatSettlementSlotId(new Date(slotEnd - slotMilliseconds));
};

// Return the stream time before which ClickHouse ingestion is complete.
// This function does not consume or acknowledge stream messages.
const getClickHouseIngestionBoundaryMilliseconds = async (
  client: Pick<RedisClientType, "xInfoGroups" | "xPending">,
  options: Pick<SettlementLoopOptions, "consumerGroup" | "stream">,
): Promise<number | null> => {
  const [pending, groups] = await Promise.all([
    client.xPending(options.stream, options.consumerGroup),
    client.xInfoGroups(options.stream),
  ]);
  const group = groups.find(
    (candidate) => candidate.name === options.consumerGroup,
  );
  if (!group) {
    throw new Error(
      `Valkey consumer group is missing: ${options.consumerGroup}`,
    );
  }
  const oldestUnacknowledgedId = pending.firstId;
  const lastDeliveredId = String(group["last-delivered-id"]);
  const ingestionBoundaryId = oldestUnacknowledgedId ?? lastDeliveredId;

  return ingestionBoundaryId === "0-0"
    ? null
    : streamMilliseconds(ingestionBoundaryId);
};

const sourceId = (settlement: OrganizationSettlement): string =>
  `${settlement.slotId}:${settlement.organizationId}`;

export const processSettlementPass = async (
  reader: GenerationSettlementReader,
  leadership: SettlementLeadership,
  ingestionProgressClient: Pick<RedisClientType, "xInfoGroups" | "xPending">,
  options: SettlementLoopOptions,
  now: Date,
  startSlotId?: string,
): Promise<SettlementPassResult> => {
  const ingestionBoundary = await getClickHouseIngestionBoundaryMilliseconds(
    ingestionProgressClient,
    options,
  );
  if (ingestionBoundary === null) {
    return {
      nextSlotId: startSlotId ?? null,
      processedSlots: 0,
      eligibleBacklogAgeSeconds: 0,
    };
  }
  const upperSlotId = getUpperEligibleSlotId(
    now,
    ingestionBoundary,
    options.settlementDelayMilliseconds,
  );
  if (!upperSlotId) {
    return {
      nextSlotId: startSlotId ?? null,
      processedSlots: 0,
      eligibleBacklogAgeSeconds: 0,
    };
  }

  let slotId = startSlotId;
  if (slotId === undefined) {
    const latestPeriodStart = await leadership.getLatestSettlementPeriodStart();
    slotId = latestPeriodStart
      ? formatSettlementSlotId(latestPeriodStart)
      : ((await reader.getEarliestSlot(upperSlotId)) ?? undefined);
  }
  let processedSlots = 0;

  while (
    slotId &&
    slotId <= upperSlotId &&
    processedSlots < options.maxSlotsPerPass
  ) {
    const period = parseSettlementSlotId(slotId);
    const settlements = await reader.getOrganizationSettlements(slotId);
    if (settlements.some((settlement) => settlement.slotId !== slotId)) {
      throw new Error(
        `ClickHouse returned a different settlement slot for ${slotId}`,
      );
    }
    const allOrganizationIds = settlements.map(
      (settlement) => settlement.organizationId,
    );
    if (new Set(allOrganizationIds).size !== allOrganizationIds.length) {
      throw new Error(
        `ClickHouse returned duplicate organizations for ${slotId}`,
      );
    }
    const chargeable = settlements.filter(
      (settlement) => settlement.totalCharge > 0n,
    );
    if (chargeable.some((settlement) => settlement.generationCount === 0n)) {
      throw new Error(
        `Chargeable settlement has no generations in slot ${slotId}`,
      );
    }
    const organizationIds = chargeable.map(
      (settlement) => settlement.organizationId,
    );
    const knownOrganizations =
      await leadership.getBillingOrganizationIds(organizationIds);
    const missingOrganization = organizationIds.find(
      (organizationId) => !knownOrganizations.has(organizationId),
    );
    if (missingOrganization) {
      throw new Error(
        `Billing account is missing for organization ${missingOrganization}`,
      );
    }
    const existingSourceIds = await leadership.getExistingSourceIds(
      chargeable.map(sourceId),
    );
    for (const settlement of chargeable) {
      if (existingSourceIds.has(sourceId(settlement))) continue;
      await leadership.postSettlement({
        generationCount: settlement.generationCount,
        organizationId: settlement.organizationId,
        periodEnd: period.end,
        periodStart: period.start,
        slotId,
        totalCharge: settlement.totalCharge,
      });
    }

    processedSlots += 1;
    slotId = formatSettlementSlotId(period.end);
  }
  return {
    nextSlotId: slotId ?? null,
    processedSlots,
    // Only fully ingested slots past their settlement delay are overdue.
    eligibleBacklogAgeSeconds:
      slotId && slotId <= upperSlotId
        ? Math.max(
            0,
            (now.getTime() -
              parseSettlementSlotId(slotId).end.getTime() -
              options.settlementDelayMilliseconds) /
              1_000,
          )
        : 0,
  };
};

const wait = async (
  milliseconds: number,
  signal: AbortSignal,
): Promise<void> => {
  await new Promise<void>((resolve) => {
    const timeout = setTimeout(resolve, milliseconds);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timeout);
        resolve();
      },
      { once: true },
    );
  });
};

export const runGenerationSettlementLoop = async (
  reader: GenerationSettlementReader,
  store: GenerationSettlementStore,
  ingestionProgressClient: Pick<RedisClientType, "xInfoGroups" | "xPending">,
  options: SettlementLoopOptions,
  signal: AbortSignal,
): Promise<void> => {
  while (!signal.aborted) {
    const leadership = await store.tryAcquireLeadership();
    if (!leadership) {
      options.onLeadership?.(false);
      await options.onReady?.();
      await wait(options.pollMilliseconds, signal);
      continue;
    }
    try {
      options.onLeadership?.(true);
      await options.onReady?.();
      let nextSlotId: string | undefined;
      while (!signal.aborted) {
        const started = process.hrtime.bigint();
        const result = await processSettlementPass(
          reader,
          leadership,
          ingestionProgressClient,
          options,
          new Date(),
          nextSlotId,
        );
        nextSlotId = result.nextSlotId ?? undefined;
        options.onPass?.(
          result,
          Number(process.hrtime.bigint() - started) / 1e9,
        );
        await wait(options.pollMilliseconds, signal);
      }
    } finally {
      options.onLeadership?.(false);
      await leadership.release();
    }
  }
};
