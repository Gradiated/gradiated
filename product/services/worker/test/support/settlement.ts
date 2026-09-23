import type {
  GenerationSettlementReader,
  GenerationSettlementStore,
  OrganizationSettlement,
  SettlementLeadership,
} from "@gradiated/control";
import { vi } from "vitest";

import type {
  IngestionBoundary,
  SettlementConfig,
  SettlementTelemetry,
} from "../../src/settlement-loop.js";

export const organizationId = "0198ad73-a200-7000-8000-000000000002";
export const otherOrganizationId = "0198ad73-a200-7000-8000-000000000003";

export const settlementConfig: SettlementConfig = {
  maxSlotsPerPass: 100,
  pollMilliseconds: 10_000,
  settlementDelayMilliseconds: 600_000,
};

export const organizationSettlement = (
  overrides: Partial<OrganizationSettlement> = {},
): OrganizationSettlement => ({
  generationCount: 1n,
  organizationId,
  slotId: "20260815T123000Z-300s-v1",
  totalCharge: 10n,
  ...overrides,
});

export type RecordingReader = GenerationSettlementReader & {
  queriedSlots: string[];
};

export const readerWithSlots = (
  slots: Record<string, OrganizationSettlement[] | Error>,
): RecordingReader => {
  const queriedSlots: string[] = [];

  return {
    queriedSlots,
    getEarliestSlot: vi.fn(async (upperSlotId: string) => {
      const eligible = Object.keys(slots)
        .filter((slotId) => slotId <= upperSlotId)
        .sort();

      return eligible[0] ?? null;
    }),
    getOrganizationSettlements: vi.fn(async (slotId: string) => {
      queriedSlots.push(slotId);

      const settlements = slots[slotId] ?? [];
      if (settlements instanceof Error) throw settlements;

      return settlements;
    }),
  };
};

export const leadership = (): SettlementLeadership => ({
  getBillingOrganizationIds: vi.fn(async (ids: string[]) => new Set(ids)),
  getExistingSourceIds: vi.fn(async () => new Set<string>()),
  getLatestSettlementPeriodStart: vi.fn(async () => null),
  postSettlement: vi.fn(async () => true),
  release: vi.fn(async () => undefined),
});

export const store = (
  leader: SettlementLeadership | null,
): GenerationSettlementStore => ({
  tryAcquireLeadership: vi.fn(async () => leader),
});

export const ingestionBoundary =
  (boundary: Date | null): IngestionBoundary =>
  async () =>
    boundary?.getTime() ?? null;

export const settlementTelemetry = (): SettlementTelemetry => ({
  setSettlementLeadership: vi.fn(),
  recordSettlementPass: vi.fn(),
  recordPass: vi.fn(),
});
