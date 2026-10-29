import { randomUUID } from "node:crypto";

import type {
  AutoTopUpClaim,
  TopUpChargeOutcome,
  TopUpChargeRecord,
  TopUpChargeStore,
  TopUpCharger,
} from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";

import { processAutoTopUpPass } from "../src/auto-top-up-loop.js";

const now = new Date("2026-10-28T12:00:00.000Z");

const charge = (
  fields: Partial<TopUpChargeRecord> = {},
): TopUpChargeRecord => ({
  id: randomUUID(),
  organizationId: randomUUID(),
  reason: "auto_top_up",
  status: "pending",
  amount: 50_000_000_000n,
  stripeCustomerId: "cus_123",
  stripePaymentMethodId: "pm_123",
  stripeInvoiceId: null,
  failure: null,
  requestKey: null,
  createdBy: null,
  createdAt: now,
  updatedAt: now,
  ...fields,
});

const fakeStore = ({
  stale = [],
  enabled = [],
  claims = new Map(),
}: {
  stale?: TopUpChargeRecord[];
  enabled?: string[];
  claims?: Map<string, AutoTopUpClaim | Error>;
} = {}) =>
  ({
    listAutoTopUpOrganizationIds: vi.fn(async () => enabled),
    abandonInactive: vi.fn(async () => 0),
    listPendingBefore: vi.fn(async () => stale),
    oldestPendingCreatedAt: vi.fn(async () => null),
    claimAutoTopUp: vi.fn(async (organizationId: string) => {
      const claim = claims.get(organizationId) ?? { status: "not_due" };
      if (claim instanceof Error) throw claim;

      return claim;
    }),
    claimTopUp: vi.fn(),
    recordRequest: vi.fn(),
    recordInvoice: vi.fn(async () => undefined),
    succeed: vi.fn(async () => undefined),
    fail: vi.fn(async () => undefined),
  }) satisfies TopUpChargeStore;

const charger = (outcome: TopUpChargeOutcome): TopUpCharger => ({
  charge: vi.fn(async () => outcome),
  resolve: vi.fn(async () => outcome),
});

const telemetry = () => ({
  recordTopUpCharge: vi.fn(),
  recordAutoTopUpRateLimited: vi.fn(),
  recordOldestPendingTopUpCharge: vi.fn(),
});

const pass = (
  store: TopUpChargeStore,
  outcome: TopUpChargeOutcome,
  metrics = telemetry(),
) =>
  processAutoTopUpPass({
    store,
    charger: charger(outcome),
    operationalBalance: async () => null,
    telemetry: metrics,
    maxPerHour: 20,
    now,
  });

const paid: TopUpChargeOutcome = {
  status: "succeeded",
  stripeInvoiceId: "in_123",
  amount: 50_000_000_000n,
};

describe("auto top-up pass", () => {
  it("credits a claimed charge that Stripe paid", async () => {
    const claimed = charge();
    const store = fakeStore({
      enabled: [claimed.organizationId],
      claims: new Map([
        [claimed.organizationId, { status: "claimed", charge: claimed }],
      ]),
    });
    const metrics = telemetry();

    await pass(store, paid, metrics);

    expect(store.claimAutoTopUp).toHaveBeenCalledWith(
      claimed.organizationId,
      expect.any(Function),
      { maxPerHour: 20, now },
    );
    expect(store.succeed).toHaveBeenCalledWith({
      chargeId: claimed.id,
      stripeInvoiceId: "in_123",
      amount: 50_000_000_000n,
    });
    expect(metrics.recordTopUpCharge).toHaveBeenCalledWith(
      "auto_top_up",
      "succeeded",
    );
    expect(metrics.recordOldestPendingTopUpCharge).toHaveBeenCalled();
  });

  it("records a declined charge", async () => {
    const claimed = charge();
    const store = fakeStore({
      enabled: [claimed.organizationId],
      claims: new Map([
        [claimed.organizationId, { status: "claimed", charge: claimed }],
      ]),
    });
    const metrics = telemetry();

    await pass(
      store,
      {
        status: "failed",
        failure: "Your card was declined.",
        code: "card_declined",
      },
      metrics,
    );

    expect(store.fail).toHaveBeenCalledWith({
      chargeId: claimed.id,
      failure: "Your card was declined.",
    });
    expect(metrics.recordTopUpCharge).toHaveBeenCalledWith(
      "auto_top_up",
      "failed",
    );
  });

  it("counts organizations that hit the hourly limit", async () => {
    const organizationId = randomUUID();
    const metrics = telemetry();

    await pass(
      fakeStore({
        enabled: [organizationId],
        claims: new Map([[organizationId, { status: "rate_limited" }]]),
      }),
      paid,
      metrics,
    );

    expect(metrics.recordAutoTopUpRateLimited).toHaveBeenCalledOnce();
  });

  it("retries stale pending charges of every kind", async () => {
    const manual = charge({
      reason: "top_up",
      createdAt: new Date(now.getTime() - 300_000),
    });
    const store = fakeStore({ stale: [manual] });

    await pass(store, paid);

    expect(store.listPendingBefore).toHaveBeenCalledWith(
      new Date(now.getTime() - 120_000),
    );
    expect(store.succeed).toHaveBeenCalledWith(
      expect.objectContaining({ chargeId: manual.id }),
    );
  });

  it("abandons inactive organizations' unstarted charges before retrying", async () => {
    const store = fakeStore({ stale: [] });

    await pass(store, paid);

    expect(store.abandonInactive).toHaveBeenCalledWith(
      new Date(now.getTime() - 2 * 60_000),
    );
    expect(
      vi.mocked(store.abandonInactive).mock.invocationCallOrder[0],
    ).toBeLessThan(
      vi.mocked(store.listPendingBefore).mock.invocationCallOrder[0]!,
    );
  });

  it("keeps going and counts the error when one organization fails", async () => {
    const broken = randomUUID();
    const claimed = charge();
    const store = fakeStore({
      enabled: [broken, claimed.organizationId],
      claims: new Map<string, AutoTopUpClaim | Error>([
        [broken, new Error("Valkey is unavailable.")],
        [claimed.organizationId, { status: "claimed", charge: claimed }],
      ]),
    });
    const metrics = telemetry();

    await pass(store, paid, metrics);

    expect(store.succeed).toHaveBeenCalledOnce();
    expect(metrics.recordTopUpCharge).toHaveBeenCalledWith(
      "auto_top_up",
      "error",
    );
  });
});
