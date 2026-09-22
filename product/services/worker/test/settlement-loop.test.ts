import type {
  GenerationSettlementReader,
  SettlementLeadership,
} from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";
import {
  formatSettlementSlotId,
  getUpperEligibleSlotId,
  parseSettlementSlotId,
  processSettlementPass,
  runGenerationSettlementLoop,
  type SettlementLoopOptions,
} from "../src/settlement-loop.js";

const organizationId = "0198ad73-a200-7000-8000-000000000002";
const zeroChargeOrganizationId = "0198ad73-a200-7000-8000-000000000003";
const slotId = "20260815T123000Z-300s-v1";

const options: SettlementLoopOptions = {
  consumerGroup: "clickhouse-generation-ingest-v1",
  maxSlotsPerPass: 100,
  pollMilliseconds: 10_000,
  settlementDelayMilliseconds: 600_000,
  stream: "generation-settled:{settlement-0}",
};

const ingestionProgressClient = (
  lastDeliveredDate: Date,
  oldestUnacknowledgedDate?: Date,
) =>
  ({
    xPending: vi.fn(async () => ({
      firstId: oldestUnacknowledgedDate
        ? `${oldestUnacknowledgedDate.getTime()}-0`
        : null,
    })),
    xInfoGroups: vi.fn(async () => [
      {
        name: options.consumerGroup,
        "last-delivered-id": `${lastDeliveredDate.getTime()}-0`,
      },
    ]),
  }) as never;

const leadership = (): SettlementLeadership => ({
  getBillingOrganizationIds: vi.fn(async (ids: string[]) => new Set(ids)),
  getExistingSourceIds: vi.fn(async () => new Set<string>()),
  getLatestSettlementPeriodStart: vi.fn(async () => null),
  postSettlement: vi.fn(async () => true),
  release: vi.fn(async () => undefined),
});

describe("generation settlement", () => {
  it("formats and parses five-minute slots", () => {
    expect(formatSettlementSlotId(new Date("2026-08-15T12:32:00.000Z"))).toBe(
      slotId,
    );
    expect(parseSettlementSlotId(slotId)).toEqual({
      start: new Date("2026-08-15T12:30:00.000Z"),
      end: new Date("2026-08-15T12:35:00.000Z"),
    });
    expect(() => parseSettlementSlotId("20260815T123100Z-300s-v1")).toThrow(
      "Invalid settlement slot ID",
    );
    expect(() => parseSettlementSlotId("20260230T123000Z-300s-v1")).toThrow(
      "Invalid settlement slot ID",
    );
  });

  it("uses the earlier of the delay and ClickHouse ingestion boundary", () => {
    expect(
      getUpperEligibleSlotId(
        new Date("2026-08-15T13:00:00.000Z"),
        new Date("2026-08-15T12:45:00.000Z").getTime(),
        600_000,
      ),
    ).toBe("20260815T124000Z-300s-v1");
  });

  it("does not pass the oldest unacknowledged ingestion event", async () => {
    const reader: GenerationSettlementReader = {
      getEarliestSlot: vi.fn(async () => "20260815T123500Z-300s-v1"),
      getOrganizationSettlements: vi.fn(async () => []),
    };

    await expect(
      processSettlementPass(
        reader,
        leadership(),
        ingestionProgressClient(
          new Date("2026-08-15T13:00:00.000Z"),
          new Date("2026-08-15T12:35:00.000Z"),
        ),
        options,
        new Date("2026-08-15T13:15:00.000Z"),
      ),
    ).resolves.toEqual({
      nextSlotId: "20260815T123500Z-300s-v1",
      processedSlots: 0,
      eligibleBacklogAgeSeconds: 0,
    });
    expect(reader.getOrganizationSettlements).not.toHaveBeenCalled();
  });

  it("posts one nonzero organization settlement", async () => {
    const reader: GenerationSettlementReader = {
      getEarliestSlot: vi.fn(async () => slotId),
      getOrganizationSettlements: vi.fn(async () => [
        {
          generationCount: 2n,
          organizationId,
          slotId,
          totalCharge: 42n,
        },
        {
          generationCount: 0n,
          organizationId: zeroChargeOrganizationId,
          slotId,
          totalCharge: 0n,
        },
      ]),
    };
    const leader = leadership();

    const result = await processSettlementPass(
      reader,
      leader,
      ingestionProgressClient(new Date("2026-08-15T12:35:00.000Z")),
      options,
      new Date("2026-08-15T12:50:00.000Z"),
    );

    expect(result).toEqual({
      nextSlotId: "20260815T123500Z-300s-v1",
      processedSlots: 1,
      eligibleBacklogAgeSeconds: 0,
    });
    expect(leader.getBillingOrganizationIds).toHaveBeenCalledWith([
      organizationId,
    ]);
    expect(leader.postSettlement).toHaveBeenCalledOnce();
    expect(leader.postSettlement).toHaveBeenCalledWith({
      generationCount: 2n,
      organizationId,
      periodEnd: new Date("2026-08-15T12:35:00.000Z"),
      periodStart: new Date("2026-08-15T12:30:00.000Z"),
      slotId,
      totalCharge: 42n,
    });
  });

  it("skips an existing organization settlement", async () => {
    const reader: GenerationSettlementReader = {
      getEarliestSlot: vi.fn(async () => slotId),
      getOrganizationSettlements: vi.fn(async () => [
        {
          generationCount: 1n,
          organizationId,
          slotId,
          totalCharge: 10n,
        },
      ]),
    };
    const leader = leadership();
    vi.mocked(leader.getExistingSourceIds).mockResolvedValue(
      new Set([`${slotId}:${organizationId}`]),
    );

    await processSettlementPass(
      reader,
      leader,
      ingestionProgressClient(new Date("2026-08-15T12:35:00.000Z")),
      options,
      new Date("2026-08-15T12:50:00.000Z"),
    );

    expect(leader.postSettlement).not.toHaveBeenCalled();
  });

  it("blocks the complete slot when an organization is missing", async () => {
    const reader: GenerationSettlementReader = {
      getEarliestSlot: vi.fn(async () => slotId),
      getOrganizationSettlements: vi.fn(async () => [
        {
          generationCount: 1n,
          organizationId,
          slotId,
          totalCharge: 10n,
        },
      ]),
    };
    const leader = leadership();
    vi.mocked(leader.getBillingOrganizationIds).mockResolvedValue(new Set());

    await expect(
      processSettlementPass(
        reader,
        leader,
        ingestionProgressClient(new Date("2026-08-15T12:35:00.000Z")),
        options,
        new Date("2026-08-15T12:50:00.000Z"),
      ),
    ).rejects.toThrow("Billing account is missing");
    expect(leader.postSettlement).not.toHaveBeenCalled();
  });

  it("returns the next slot after a bounded empty batch", async () => {
    const reader: GenerationSettlementReader = {
      getEarliestSlot: vi.fn(async () => slotId),
      getOrganizationSettlements: vi.fn(async () => []),
    };

    await expect(
      processSettlementPass(
        reader,
        leadership(),
        ingestionProgressClient(new Date("2026-08-15T13:00:00.000Z")),
        { ...options, maxSlotsPerPass: 1 },
        new Date("2026-08-15T13:15:00.000Z"),
      ),
    ).resolves.toEqual({
      nextSlotId: "20260815T123500Z-300s-v1",
      processedSlots: 1,
      eligibleBacklogAgeSeconds: 1500,
    });
  });
  it("does not report backlog when a full batch catches up", async () => {
    const result = await processSettlementPass(
      {
        getEarliestSlot: vi.fn(async () => slotId),
        getOrganizationSettlements: vi.fn(async () => []),
      },
      leadership(),
      ingestionProgressClient(new Date("2026-08-15T12:35:00Z")),
      { ...options, maxSlotsPerPass: 1 },
      new Date("2026-08-15T13:15:00Z"),
    );
    expect(result.processedSlots).toBe(1);
    expect(result.eligibleBacklogAgeSeconds).toBe(0);
  });

  it("does not treat an idle stream as settlement backlog", async () => {
    const result = await processSettlementPass(
      {
        getEarliestSlot: vi.fn(async () => null),
        getOrganizationSettlements: vi.fn(async () => []),
      },
      leadership(),
      ingestionProgressClient(new Date("2026-08-15T12:35:00Z")),
      options,
      new Date("2026-08-16T13:15:00Z"),
    );
    expect(result.eligibleBacklogAgeSeconds).toBe(0);
  });
  it("reports leadership and releases it even if readiness fails", async () => {
    const leader = leadership();
    const onLeadership = vi.fn();
    await expect(
      runGenerationSettlementLoop(
        {
          getEarliestSlot: vi.fn(async () => null),
          getOrganizationSettlements: vi.fn(async () => []),
        },
        { tryAcquireLeadership: vi.fn(async () => leader) } as never,
        ingestionProgressClient(new Date("2026-08-15T12:35:00Z")),
        {
          ...options,
          onLeadership,
          onReady: async () => {
            throw new Error("readiness failed");
          },
        },
        new AbortController().signal,
      ),
    ).rejects.toThrow("readiness failed");
    expect(onLeadership.mock.calls).toEqual([[true], [false]]);
    expect(leader.release).toHaveBeenCalledOnce();
  });
});
