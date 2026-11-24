// The official TypeSafe SDK (`@typesafe-ai/sdk`, pinned in package.json) pointed at
// a gateway or proxy, plus the assertions its error classes need.
import {
  APIError,
  TypeSafeClient,
  type Fetch,
  type TypeSafeClientConfig,
} from "@typesafe-ai/sdk";
import { expect } from "vitest";

import type { Case } from "./case.js";
import type { ErrorCode } from "./assertions.js";
import { eventually } from "./eventually.js";
import type { JsonObject } from "./json.js";

/** A client for one case: its key, its model and no retries unless a test asks. */
export const typesafeClient = (
  instance: Case,
  config: TypeSafeClientConfig = {},
  baseUrl: string = instance.http.baseUrl,
): TypeSafeClient =>
  new TypeSafeClient({
    apiKey: instance.key,
    // The SDK adds `/v1/systemone` itself.
    baseURL: baseUrl.replace(/\/+$/, ""),
    defaultModel: instance.model,
    retry: { maxRetries: 0 },
    timeout: 5000,
    logLevel: "off",
    ...config,
  });

export interface Attempt {
  readonly url: string;
  readonly headers: Headers;
}

/** A fetch that records every attempt the SDK makes, retries included. */
export const countingFetch = (): { fetch: Fetch; attempts: Attempt[] } => {
  const attempts: Attempt[] = [];
  const fetch: Fetch = (input, init) => {
    attempts.push({ url: input, headers: new Headers(init?.headers) });
    return globalThis.fetch(input, init);
  };

  return { fetch, attempts };
};

/** Retries without waiting, so retry tests stay fast. */
export const IMMEDIATE_RETRIES = {
  backoffInitialMs: 1,
  backoffMaxMs: 1,
  backoffJitter: 0,
} as const;

export const headerRecord = (headers: Headers): Record<string, string> => {
  const record: Record<string, string> = {};
  headers.forEach((value, key) => (record[key] = value));
  return record;
};

/** Resolves to what the call rejected with, and fails if it succeeded. */
export const rejection = async (call: Promise<unknown>): Promise<unknown> =>
  call.then(
    () => {
      throw new Error("expected the SDK call to fail");
    },
    (error: unknown) => error,
  );

type ApiErrorClass = abstract new (...args: never[]) => APIError;

/**
 * Checks the SDK's error class, the HTTP status and the gateway's public error
 * code. `exact` requires the class itself rather than a subclass, for statuses
 * the SDK has no subclass for (402, 413).
 */
export const expectSdkError = (
  error: unknown,
  kind: ApiErrorClass,
  expected: {
    status: number;
    code: ErrorCode | string;
    param?: string | null;
    exact?: boolean;
  },
): APIError => {
  expect(error).toBeInstanceOf(kind);
  if (expected.exact) {
    expect(Object.getPrototypeOf(error)).toBe(kind.prototype);
  }
  const api = error as APIError;
  expect(api.status, JSON.stringify(api.body)).toBe(expected.status);
  expect(api.body).toMatchObject({ error: { code: expected.code } });
  if (expected.param !== undefined) {
    expect((api.body as { error: { param: unknown } }).error.param).toBe(
      expected.param,
    );
  }

  return api;
};

/** The settlement of the case's only generation, for calls that never got a response. */
export const onlySettlement = async (instance: Case): Promise<JsonObject> => {
  const rows = await eventually(
    async () => {
      const rows = await instance.settlements();
      return rows.length > 0 ? rows : undefined;
    },
    5000,
    "the abandoned generation was never settled",
  );
  expect(rows).toHaveLength(1);

  return rows[0]!.properties;
};

/** Cancelled requests release their admission lease asynchronously. */
export const leaseReleased = async (instance: Case): Promise<void> => {
  await eventually(
    async () => (await instance.redis.zCard(instance.inflightKey)) === 0,
    5000,
    "admission lease was never released",
  );
};
