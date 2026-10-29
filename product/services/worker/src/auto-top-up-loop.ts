import {
  settleTopUpCharge,
  type TopUpCharger,
  type TopUpChargeRecord,
  type TopUpChargeStore,
  type OperationalBalanceReader,
} from "@gradiated/control";

import { serviceLog } from "./logging.js";
import type { WorkerMetrics } from "./metrics.js";

// A younger pending charge may still be in flight in the API or another worker.
const PENDING_RETRY_MILLISECONDS = 2 * 60_000;

export type AutoTopUpPass = {
  store: TopUpChargeStore;
  charger: TopUpCharger;
  operationalBalance: OperationalBalanceReader;
  telemetry: Pick<
    WorkerMetrics,
    | "recordTopUpCharge"
    | "recordAutoTopUpRateLimited"
    | "recordOldestPendingTopUpCharge"
  >;
  maxPerHour: number;
  now: Date;
};

const settle = async (
  pass: AutoTopUpPass,
  charge: TopUpChargeRecord,
): Promise<void> => {
  const settled = await settleTopUpCharge(pass, charge);
  const fields = {
    organization_id: charge.organizationId,
    reason: charge.reason,
  };

  pass.telemetry.recordTopUpCharge(charge.reason, settled.status);

  if (settled.status === "succeeded") {
    serviceLog("info", "top_up_charge_succeeded", fields);
  } else if (settled.status === "failed") {
    serviceLog("warn", "top_up_charge_failed", {
      ...fields,
      reason: `${charge.reason}:${settled.code}`,
    });
  } else {
    serviceLog("info", "top_up_charge_processing", fields);
  }
};

const isolate = async (
  pass: AutoTopUpPass,
  organizationId: string,
  reason: TopUpChargeRecord["reason"],
  work: () => Promise<void>,
): Promise<void> => {
  try {
    await work();
  } catch (error) {
    pass.telemetry.recordTopUpCharge(reason, "error");
    serviceLog("error", "top_up_charge_error", {
      organization_id: organizationId,
      reason,
      error,
    });
  }
};

export const processAutoTopUpPass = async (
  pass: AutoTopUpPass,
): Promise<void> => {
  const { store, operationalBalance, maxPerHour, now } = pass;
  const retryBefore = new Date(now.getTime() - PENDING_RETRY_MILLISECONDS);
  // Charges that never reached Stripe are not retried for inactive organizations.
  await store.abandonInactive(retryBefore);

  const stale = await store.listPendingBefore(retryBefore);

  for (const charge of stale) {
    await isolate(pass, charge.organizationId, charge.reason, () =>
      settle(pass, charge),
    );
  }

  for (const organizationId of await store.listAutoTopUpOrganizationIds()) {
    await isolate(pass, organizationId, "auto_top_up", async () => {
      const claim = await store.claimAutoTopUp(
        organizationId,
        operationalBalance,
        { maxPerHour, now },
      );

      if (claim.status === "rate_limited") {
        pass.telemetry.recordAutoTopUpRateLimited();
        serviceLog("warn", "auto_top_up_rate_limited", {
          organization_id: organizationId,
        });
      } else if (claim.status === "claimed") {
        await settle(pass, claim.charge);
      }
    });
  }

  pass.telemetry.recordOldestPendingTopUpCharge(
    await store.oldestPendingCreatedAt(),
    new Date(),
  );
};
