import { createGenerationSettlementStore } from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";

const organizationId = "0198ad73-a200-7000-8000-000000000002";
const slotId = "20260815T123000Z-300s-v1";

describe("PostgreSQL generation settlement store", () => {
  it("posts one balance movement and updates the account in one transaction", async () => {
    const query = vi
      .fn()
      .mockResolvedValueOnce({ rows: [{ acquired: true }] })
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ balance: "1000" }] })
      .mockResolvedValueOnce({ rowCount: 0, rows: [] })
      .mockResolvedValueOnce({ rowCount: 1, rows: [] })
      .mockResolvedValueOnce({ rowCount: 1, rows: [] })
      .mockResolvedValueOnce({ rows: [] });
    const release = vi.fn();
    const store = createGenerationSettlementStore({
      connect: vi.fn(async () => ({ query, release })),
    } as never);
    const leadership = await store.tryAcquireLeadership();

    expect(leadership).not.toBeNull();
    await expect(
      leadership?.postSettlement({
        generationCount: 2n,
        organizationId,
        periodEnd: new Date("2026-08-15T12:35:00.000Z"),
        periodStart: new Date("2026-08-15T12:30:00.000Z"),
        slotId,
        totalCharge: 42n,
      }),
    ).resolves.toBe(true);

    expect(query.mock.calls[1]?.[0]).toBe("BEGIN");
    expect(query.mock.calls[4]?.[1]).toEqual([
      expect.any(String),
      organizationId,
      "-42",
      "958",
      `${slotId}:${organizationId}`,
      new Date("2026-08-15T12:30:00.000Z"),
      new Date("2026-08-15T12:35:00.000Z"),
      "2",
      expect.any(Date),
    ]);
    expect(query.mock.calls[5]?.[1]).toEqual([
      "958",
      expect.any(Date),
      organizationId,
    ]);
    expect(query.mock.calls[6]?.[0]).toBe("COMMIT");
  });

  it("does not post an existing source ID", async () => {
    const query = vi
      .fn()
      .mockResolvedValueOnce({ rows: [{ acquired: true }] })
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [{ balance: "1000" }] })
      .mockResolvedValueOnce({ rowCount: 1, rows: [{ exists: 1 }] })
      .mockResolvedValueOnce({ rows: [] });
    const store = createGenerationSettlementStore({
      connect: vi.fn(async () => ({ query, release: vi.fn() })),
    } as never);
    const leadership = await store.tryAcquireLeadership();

    await expect(
      leadership?.postSettlement({
        generationCount: 2n,
        organizationId,
        periodEnd: new Date("2026-08-15T12:35:00.000Z"),
        periodStart: new Date("2026-08-15T12:30:00.000Z"),
        slotId,
        totalCharge: 42n,
      }),
    ).resolves.toBe(false);
    expect(query).toHaveBeenCalledTimes(5);
    expect(query.mock.calls[4]?.[0]).toBe("COMMIT");
  });

  it("releases the database client when another replica is leader", async () => {
    const query = vi.fn(async () => ({ rows: [{ acquired: false }] }));
    const release = vi.fn();
    const store = createGenerationSettlementStore({
      connect: vi.fn(async () => ({ query, release })),
    } as never);

    await expect(store.tryAcquireLeadership()).resolves.toBeNull();
    expect(release).toHaveBeenCalledOnce();
  });
});
