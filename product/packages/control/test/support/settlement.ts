import type { SettlementPosting } from "../../src/settlement/postgres-store.js";

export const slotId = "20260815T123000Z-300s-v1";
export const periodStart = new Date("2026-08-15T12:30:00.000Z");
export const periodEnd = new Date("2026-08-15T12:35:00.000Z");

export const settlementPosting = (
  organizationId: string,
  overrides: Partial<SettlementPosting> = {},
): SettlementPosting => ({
  generationCount: 3n,
  organizationId,
  periodEnd,
  periodStart,
  slotId,
  totalCharge: 250n,
  ...overrides,
});
