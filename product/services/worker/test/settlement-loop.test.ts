import {
  BalanceSourceConflictError,
  SettlementFinancialConflictError,
  type SettlementLeadership,
} from "@gradiated/control";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  processSettlementPass,
  runGenerationSettlementLoop,
  type SettlementLoop,
  type SettlementPass,
  type SettlementTelemetry,
  upperEligibleSlot,
} from "../src/settlement-loop.js";
import { parseSlot } from "../src/settlement-slot.js";
import {
  ingestionBoundary,
  leadership,
  organizationId,
  organizationSettlement,
  otherOrganizationId,
  readerWithSlots,
  settlementConfig as config,
  settlementTelemetry,
  store,
} from "./support/settlement.js";

const slot1225 = "20260815T122500Z-300s-v1";
const slot1230 = "20260815T123000Z-300s-v1";
const slot1235 = "20260815T123500Z-300s-v1";
const slot1240 = "20260815T124000Z-300s-v1";
const slot1245 = "20260815T124500Z-300s-v1";
const slot1250 = "20260815T125000Z-300s-v1";

const at = (time: string) => new Date(`2026-08-15T${time}:00.000Z`);

const posting = (slotId: string, organization: string, totalCharge: bigint) => {
  const period = parseSlot(slotId);

  return {
    generationCount: 1n,
    organizationId: organization,
    periodEnd: period.end,
    periodStart: period.start,
    slotId,
    totalCharge,
  };
};

const postedSlots = (leader: SettlementLeadership) =>
  vi
    .mocked(leader.postSettlement)
    .mock.calls.map(([posted]) => [posted.slotId, posted.organizationId]);

describe("upper eligible slot", () => {
  it("uses the earlier of the delay and the ingestion boundary", () => {
    expect(
      upperEligibleSlot(at("13:00"), at("12:45").getTime(), 600_000)?.id,
    ).toBe(slot1240);
  });

  it("has no eligible slot before the first slot ends", () => {
    expect(upperEligibleSlot(new Date(599_999), 299_999, 300_000)).toBeNull();
  });
});

const runPass = (overrides: Partial<SettlementPass> = {}) =>
  processSettlementPass({
    reader: readerWithSlots({}),
    leadership: leadership(),
    ingestionBoundary: ingestionBoundary(at("12:35")),
    config,
    now: at("12:50"),
    cursor: null,
    ...overrides,
  });

describe("settlement pass", () => {
  it("does not pass the ingestion boundary", async () => {
    const reader = readerWithSlots({ [slot1235]: [organizationSettlement()] });

    const result = await runPass({
      reader,
      now: at("13:15"),
      cursor: parseSlot(slot1235),
    });

    expect(result).toEqual({
      cursor: parseSlot(slot1235),
      processedSlots: 0,
      eligibleBacklogAgeSeconds: 0,
    });
    expect(reader.queriedSlots).toEqual([]);
  });

  it("does no work and keeps the cursor before any entry is ingested", async () => {
    const reader = readerWithSlots({ [slot1230]: [organizationSettlement()] });
    const leader = leadership();

    const result = await runPass({
      reader,
      leadership: leader,
      ingestionBoundary: ingestionBoundary(null),
      now: at("13:15"),
      cursor: parseSlot(slot1235),
    });

    expect(result).toEqual({
      cursor: parseSlot(slot1235),
      processedSlots: 0,
      eligibleBacklogAgeSeconds: 0,
    });
    expect(reader.getEarliestSlot).not.toHaveBeenCalled();
    expect(reader.queriedSlots).toEqual([]);
    expect(leader.getLatestSettlementPeriodStart).not.toHaveBeenCalled();
  });

  it("posts one nonzero organization settlement", async () => {
    const reader = readerWithSlots({
      [slot1230]: [
        organizationSettlement({ generationCount: 2n, totalCharge: 42n }),
        organizationSettlement({
          generationCount: 0n,
          organizationId: otherOrganizationId,
          totalCharge: 0n,
        }),
      ],
    });
    const leader = leadership();

    const result = await runPass({
      reader,
      leadership: leader,
    });

    expect(result).toEqual({
      cursor: parseSlot(slot1235),
      processedSlots: 1,
      eligibleBacklogAgeSeconds: 0,
    });
    expect(leader.getBillingOrganizationIds).toHaveBeenCalledWith([
      organizationId,
    ]);
    expect(leader.postSettlement).toHaveBeenCalledOnce();
    expect(leader.postSettlement).toHaveBeenCalledWith({
      ...posting(slot1230, organizationId, 42n),
      generationCount: 2n,
    });
  });

  it("resumes at the latest posted period and replays its postings", async () => {
    const reader = readerWithSlots({
      [slot1225]: [organizationSettlement({ slotId: slot1225 })],
      [slot1230]: [
        organizationSettlement({ slotId: slot1230 }),
        organizationSettlement({
          organizationId: otherOrganizationId,
          slotId: slot1230,
          totalCharge: 5n,
        }),
      ],
      [slot1235]: [
        organizationSettlement({ slotId: slot1235, totalCharge: 7n }),
      ],
    });
    const leader = leadership();
    vi.mocked(leader.getLatestSettlementPeriodStart).mockResolvedValue(
      at("12:30"),
    );
    vi.mocked(leader.postSettlement).mockResolvedValueOnce(false);

    const result = await runPass({
      reader,
      leadership: leader,
      ingestionBoundary: ingestionBoundary(at("12:40")),
      now: at("13:00"),
    });

    expect(reader.getEarliestSlot).not.toHaveBeenCalled();
    expect(reader.queriedSlots).toEqual([slot1230, slot1235]);
    expect(vi.mocked(leader.postSettlement).mock.calls).toEqual([
      [posting(slot1230, organizationId, 10n)],
      [posting(slot1230, otherOrganizationId, 5n)],
      [posting(slot1235, organizationId, 7n)],
    ]);
    expect(result).toEqual({
      cursor: parseSlot(slot1240),
      processedSlots: 2,
      eligibleBacklogAgeSeconds: 0,
    });
  });

  it("stops at a posted settlement whose amount differs from ClickHouse", async () => {
    const reader = readerWithSlots({
      [slot1230]: [
        organizationSettlement({ slotId: slot1230 }),
        organizationSettlement({
          organizationId: otherOrganizationId,
          slotId: slot1230,
        }),
      ],
    });
    const leader = leadership();
    const conflict = new BalanceSourceConflictError(
      "generation_settlement_batch",
      `${slot1230}:${organizationId}`,
    );
    vi.mocked(leader.postSettlement).mockRejectedValueOnce(conflict);

    const pass = runPass({
      reader,
      leadership: leader,
    });

    await expect(pass).rejects.toMatchObject({
      code: "ESETTLEMENT_CONFLICT",
      cause: conflict,
    });
    expect(postedSlots(leader)).toEqual([[slot1230, organizationId]]);
  });

  it("keeps a ledger failure that is not a conflict unchanged", async () => {
    const reader = readerWithSlots({ [slot1230]: [organizationSettlement()] });
    const leader = leadership();
    const failure = new Error("PostgreSQL unavailable");
    vi.mocked(leader.postSettlement).mockRejectedValueOnce(failure);

    const pass = runPass({
      reader,
      leadership: leader,
    });

    await expect(pass).rejects.toBe(failure);
  });

  it("stops at a slot where one generation has conflicting financial values", async () => {
    const conflict = new SettlementFinancialConflictError(slot1230);
    const reader = readerWithSlots({
      [slot1225]: [organizationSettlement({ slotId: slot1225 })],
      [slot1230]: conflict,
    });
    const leader = leadership();

    const pass = runPass({
      reader,
      leadership: leader,
    });

    await expect(pass).rejects.toMatchObject({
      code: "EGENERATION_FINANCIAL_CONFLICT",
      cause: conflict,
    });
    expect(postedSlots(leader)).toEqual([[slot1225, organizationId]]);
  });

  it("rejects a malformed slot before it reads billing accounts", async () => {
    const reader = readerWithSlots({
      [slot1230]: [
        organizationSettlement({ slotId: slot1230 }),
        organizationSettlement({ slotId: slot1230 }),
      ],
    });
    const leader = leadership();

    const pass = runPass({
      reader,
      leadership: leader,
    });

    await expect(pass).rejects.toMatchObject({
      code: "EDUPLICATE_ORGANIZATION",
    });
    expect(leader.getBillingOrganizationIds).not.toHaveBeenCalled();
  });

  it("walks consecutive slots in order and stops at the upper eligible slot", async () => {
    const reader = readerWithSlots({
      [slot1230]: [organizationSettlement({ slotId: slot1230 })],
      [slot1240]: [organizationSettlement({ slotId: slot1240 })],
      [slot1250]: [organizationSettlement({ slotId: slot1250 })],
    });
    const leader = leadership();

    const result = await runPass({
      reader,
      leadership: leader,
      ingestionBoundary: ingestionBoundary(at("12:45")),
      now: at("13:15"),
    });

    expect(reader.queriedSlots).toEqual([slot1230, slot1235, slot1240]);
    expect(postedSlots(leader)).toEqual([
      [slot1230, organizationId],
      [slot1240, organizationId],
    ]);
    expect(result).toEqual({
      cursor: parseSlot(slot1245),
      processedSlots: 3,
      eligibleBacklogAgeSeconds: 0,
    });
  });

  it("stops at the slot limit and reports the eligible backlog age", async () => {
    const reader = readerWithSlots({
      [slot1230]: [organizationSettlement({ slotId: slot1230 })],
      [slot1235]: [organizationSettlement({ slotId: slot1235 })],
      [slot1240]: [organizationSettlement({ slotId: slot1240 })],
    });
    const leader = leadership();

    const result = await runPass({
      reader,
      leadership: leader,
      ingestionBoundary: ingestionBoundary(at("13:00")),
      config: { ...config, maxSlotsPerPass: 2 },
      now: at("13:15"),
    });

    expect(reader.queriedSlots).toEqual([slot1230, slot1235]);
    expect(leader.postSettlement).toHaveBeenCalledTimes(2);
    expect(result).toEqual({
      cursor: parseSlot(slot1240),
      processedSlots: 2,
      eligibleBacklogAgeSeconds: 1_200,
    });
  });

  it("returns the next slot after a bounded empty batch", async () => {
    const reader = readerWithSlots({ [slot1230]: [] });

    const result = await runPass({
      reader,
      ingestionBoundary: ingestionBoundary(at("13:00")),
      config: { ...config, maxSlotsPerPass: 1 },
      now: at("13:15"),
    });

    expect(result).toEqual({
      cursor: parseSlot(slot1235),
      processedSlots: 1,
      eligibleBacklogAgeSeconds: 1_500,
    });
  });

  it("does not report backlog when a full batch catches up", async () => {
    const reader = readerWithSlots({ [slot1230]: [] });

    const result = await runPass({
      reader,
      config: { ...config, maxSlotsPerPass: 1 },
      now: at("13:15"),
    });

    expect(result.processedSlots).toBe(1);
    expect(result.eligibleBacklogAgeSeconds).toBe(0);
  });

  it("does not treat an idle stream as settlement backlog", async () => {
    const result = await runPass({
      now: new Date("2026-08-16T13:15:00Z"),
    });

    expect(result.eligibleBacklogAgeSeconds).toBe(0);
  });

  it.each([
    [
      "ESLOT_MISMATCH",
      organizationSettlement({
        organizationId: otherOrganizationId,
        slotId: slot1235,
      }),
    ],
    ["EDUPLICATE_ORGANIZATION", organizationSettlement({ slotId: slot1230 })],
    [
      "ECHARGE_WITHOUT_GENERATIONS",
      organizationSettlement({
        organizationId: otherOrganizationId,
        slotId: slot1230,
        generationCount: 0n,
      }),
    ],
    [
      "EMISSING_BILLING_ACCOUNT",
      organizationSettlement({
        organizationId: otherOrganizationId,
        slotId: slot1230,
      }),
    ],
  ])(
    "rejects the whole slot with %s before it posts any organization",
    async (code, invalid) => {
      const reader = readerWithSlots({
        [slot1225]: [organizationSettlement({ slotId: slot1225 })],
        [slot1230]: [organizationSettlement({ slotId: slot1230 }), invalid],
      });
      const leader = leadership();
      vi.mocked(leader.getBillingOrganizationIds).mockResolvedValue(
        new Set([organizationId]),
      );

      const pass = runPass({
        reader,
        leadership: leader,
      });

      await expect(pass).rejects.toMatchObject({ code });
      expect(postedSlots(leader)).toEqual([[slot1225, organizationId]]);
    },
  );
});

describe("settlement loop", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const runLoop = (
    overrides: Partial<SettlementLoop> & Pick<SettlementLoop, "store">,
  ) =>
    runGenerationSettlementLoop({
      reader: readerWithSlots({}),
      ingestionBoundary: ingestionBoundary(at("12:45")),
      config: { ...config, pollMilliseconds: 60_000 },
      telemetry: settlementTelemetry(),
      onReady: async () => undefined,
      signal: new AbortController().signal,
      ...overrides,
    });

  const leadershipReports = (telemetry: SettlementTelemetry) =>
    vi.mocked(telemetry.setSettlementLeadership).mock.calls;

  it("carries the cursor from one pass to the next", async () => {
    const reader = readerWithSlots({
      [slot1230]: [organizationSettlement({ slotId: slot1230 })],
      [slot1235]: [organizationSettlement({ slotId: slot1235 })],
    });
    const leader = leadership();
    const controller = new AbortController();
    const telemetry = settlementTelemetry();
    vi.mocked(telemetry.recordSettlementPass).mockImplementation(() => {
      if (reader.queriedSlots.length === 2) controller.abort();
    });

    await runLoop({
      reader,
      store: store(leader),
      config: { ...config, maxSlotsPerPass: 1, pollMilliseconds: 0 },
      telemetry,
      signal: controller.signal,
    });

    expect(reader.getEarliestSlot).toHaveBeenCalledOnce();
    expect(leader.getLatestSettlementPeriodStart).toHaveBeenCalledOnce();
    expect(reader.queriedSlots).toEqual([slot1230, slot1235]);
    expect(telemetry.recordSettlementPass).toHaveBeenCalledTimes(2);
    expect(telemetry.recordPass).toHaveBeenCalledWith(
      "settlement",
      expect.any(Number),
    );
    expect(leader.release).toHaveBeenCalledOnce();
  });

  it("finishes the current slot and releases leadership without starting another on shutdown", async () => {
    const controller = new AbortController();
    const reader = readerWithSlots({
      [slot1230]: [organizationSettlement({ slotId: slot1230 })],
      [slot1235]: [organizationSettlement({ slotId: slot1235 })],
    });
    const leader = leadership();
    vi.mocked(leader.postSettlement).mockImplementation(async () => {
      controller.abort();
      expect(leader.release).not.toHaveBeenCalled();
      return true;
    });

    await runLoop({ reader, store: store(leader), signal: controller.signal });

    expect(reader.queriedSlots).toEqual([slot1230]);
    expect(leader.postSettlement).toHaveBeenCalledOnce();
    expect(leader.release).toHaveBeenCalledOnce();
  });

  it("stops promptly when aborted during a pass", async () => {
    const controller = new AbortController();
    const leader = leadership();
    const telemetry = settlementTelemetry();
    vi.mocked(telemetry.recordSettlementPass).mockImplementation(() =>
      controller.abort(),
    );

    await runLoop({
      store: store(leader),
      telemetry,
      signal: controller.signal,
    });

    expect(leader.release).toHaveBeenCalledOnce();
  });

  it("waits without reading ClickHouse while another replica leads", async () => {
    const reader = readerWithSlots({ [slot1230]: [organizationSettlement()] });
    const settlementStore = store(null);
    const controller = new AbortController();
    const telemetry = settlementTelemetry();
    const onReady = vi.fn(async () => controller.abort());

    await runLoop({
      reader,
      store: settlementStore,
      telemetry,
      onReady,
      signal: controller.signal,
    });

    expect(settlementStore.tryAcquireLeadership).toHaveBeenCalledOnce();
    expect(leadershipReports(telemetry)).toEqual([[false]]);
    expect(onReady).toHaveBeenCalledOnce();
    expect(reader.getEarliestSlot).not.toHaveBeenCalled();
    expect(reader.queriedSlots).toEqual([]);
  });

  it("ends during the poll wait and releases leadership once", async () => {
    const controller = new AbortController();
    const leader = leadership();
    const telemetry = settlementTelemetry();
    vi.mocked(telemetry.recordSettlementPass).mockImplementation(() => {
      setTimeout(() => controller.abort(), 10);
    });

    await runLoop({
      store: store(leader),
      telemetry,
      signal: controller.signal,
    });

    expect(leadershipReports(telemetry)).toEqual([[true], [false]]);
    expect(leader.release).toHaveBeenCalledOnce();
  });

  it("keeps earlier postings and releases leadership when a read fails", async () => {
    const reader = readerWithSlots({
      [slot1230]: [organizationSettlement({ slotId: slot1230 })],
      [slot1235]: new Error("ClickHouse unavailable"),
    });
    const leader = leadership();
    const telemetry = settlementTelemetry();

    const loop = runLoop({ reader, store: store(leader), telemetry });

    await expect(loop).rejects.toThrow("ClickHouse unavailable");
    expect(postedSlots(leader)).toEqual([[slot1230, organizationId]]);
    expect(leadershipReports(telemetry)).toEqual([[true], [false]]);
    expect(leader.release).toHaveBeenCalledOnce();
  });

  it("reports leadership and releases it even if readiness fails", async () => {
    const leader = leadership();
    const telemetry = settlementTelemetry();

    const loop = runLoop({
      store: store(leader),
      ingestionBoundary: ingestionBoundary(at("12:35")),
      telemetry,
      onReady: async () => {
        throw new Error("readiness failed");
      },
    });

    await expect(loop).rejects.toThrow("readiness failed");
    expect(leadershipReports(telemetry)).toEqual([[true], [false]]);
    expect(leader.release).toHaveBeenCalledOnce();
  });

  it("surfaces the pass failure and logs a failed release", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const leader = leadership();
    vi.mocked(leader.release).mockRejectedValue(new Error("connection lost"));

    const loop = runLoop({
      reader: readerWithSlots({
        [slot1230]: new Error("ClickHouse unavailable"),
      }),
      store: store(leader),
    });

    await expect(loop).rejects.toThrow("ClickHouse unavailable");
    expect(log.mock.calls.map(([line]) => JSON.parse(String(line)))).toEqual([
      expect.objectContaining({
        event: "settlement_release_failed",
        level: "error",
        loop: "settlement",
        dependency: "postgres",
        error_type: "Error",
      }),
    ]);
  });

  it("propagates a failed release after a clean stop", async () => {
    const controller = new AbortController();
    const leader = leadership();
    vi.mocked(leader.release).mockRejectedValue(new Error("connection lost"));

    const loop = runLoop({
      store: store(leader),
      onReady: async () => controller.abort(),
      signal: controller.signal,
    });

    await expect(loop).rejects.toThrow("connection lost");
  });
});
