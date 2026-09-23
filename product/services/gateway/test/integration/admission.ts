import { expect } from "vitest";

import type { Case } from "./case.js";
import { deferred, within } from "./eventually.js";
import { ORGANIZATION_CONCURRENCY_CAP } from "./gateway-process.js";
import type { Response } from "./http-client.js";
import type { Plan } from "./mock-runtimes/server.js";

const ENTRY_TIMEOUT_MS = 2000;

export const entered = async (plan: Plan): Promise<void> => {
  const arrival = await within(plan.entered.promise, ENTRY_TIMEOUT_MS);

  expect(arrival.settled, "runtime never received the gated request").toBe(
    true,
  );
};

export interface HeldRequests {
  readonly requests: Promise<Response>[];
  readonly release: () => void;
}

/** Holds requests open in the runtime until the organization reaches its cap. */
export const fillConcurrencyCap = async (
  instance: Case,
): Promise<HeldRequests> => {
  const gates = Array.from({ length: ORGANIZATION_CONCURRENCY_CAP }, () =>
    deferred(),
  );
  const plans = gates.map((gate) => instance.runtimes[0]!.enqueue({ gate }));
  const requests: Promise<Response>[] = [];
  const release = (): void => {
    for (const gate of gates) gate.resolve();
  };

  try {
    for (const plan of plans) {
      requests.push(instance.post());
      await entered(plan);
    }
  } catch (error) {
    release();
    throw error;
  }

  return { requests, release };
};
