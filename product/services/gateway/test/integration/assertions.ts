import { expect } from "vitest";

import type { Case } from "./case.js";
import { eventually } from "./eventually.js";
import { RECORD_CACHE_TTL_SECONDS } from "./gateway-process.js";
import type { Response } from "./http-client.js";

const SCHEDULING_MARGIN_MS = 3000;

export const PROPAGATION_DEADLINE_MS =
  RECORD_CACHE_TTL_SECONDS * 1000 + SCHEDULING_MARGIN_MS;

type ErrorType =
  | "invalid_request_error"
  | "authentication_error"
  | "permission_error"
  | "rate_limit_error"
  | "api_error";

// SDKs branch on the status and `type`, so the suite pins both to each code
// independently of the gateway's own mapping.
const PUBLIC_ERRORS = {
  invalid_request: { status: 400, type: "invalid_request_error" },
  unsupported_parameter: { status: 400, type: "invalid_request_error" },
  context_length_exceeded: { status: 400, type: "invalid_request_error" },
  payload_too_large: { status: 413, type: "invalid_request_error" },
  invalid_api_key: { status: 401, type: "authentication_error" },
  provider_key_required: { status: 401, type: "authentication_error" },
  workspace_archived: { status: 403, type: "permission_error" },
  organization_suspended: { status: 403, type: "permission_error" },
  provider_unavailable: { status: 502, type: "api_error" },
  provider_timeout: { status: 504, type: "api_error" },
  proxy_overloaded: { status: 503, type: "api_error" },
  insufficient_balance: { status: 402, type: "invalid_request_error" },
  concurrency_exceeded: { status: 429, type: "rate_limit_error" },
  settlement_backlog: { status: 429, type: "rate_limit_error" },
  capacity_exceeded: { status: 429, type: "rate_limit_error" },
  model_not_found: { status: 404, type: "invalid_request_error" },
  model_unavailable: { status: 404, type: "invalid_request_error" },
  serving_state_unavailable: { status: 503, type: "api_error" },
  runtime_unavailable: { status: 503, type: "api_error" },
  finalization_unavailable: { status: 503, type: "api_error" },
} as const satisfies Record<string, { status: number; type: ErrorType }>;

export type ErrorCode = keyof typeof PUBLIC_ERRORS;

export interface Rejection {
  readonly code: ErrorCode;
  readonly param?: string | null;
}

export const expectPublicError = (
  response: Response,
  { code, param }: Rejection,
): void => {
  const { status, type } = PUBLIC_ERRORS[code];

  expect(response.status, response.text).toBe(status);
  expect(response.error()).toMatchObject({ code, type });
  if (param !== undefined) expect(response.error().param).toBe(param);
};

/** An inference request that was refused still carries its generation ID. */
export const expectRejected = (
  response: Response,
  rejection: Rejection,
): void => {
  expectPublicError(response, rejection);
  expect(response.headers["x-generation-id"]).toBeTruthy();
};

/**
 * Sends requests until one is rejected as expected, within the propagation
 * deadline measured from `since`, and returns how many requests the gateway
 * still served before it.
 */
export const pollUntilRejected = async (
  instance: Case,
  since: number,
  rejection: Rejection,
): Promise<number> => {
  let served = 0;

  const response = await eventually(
    async () => {
      const response = await instance.post();
      if (response.status === 200) {
        served += 1;
        return undefined;
      }

      return response;
    },
    since + PROPAGATION_DEADLINE_MS - Date.now(),
    `no ${rejection.code} rejection`,
  );

  expectRejected(response, rejection);

  return served;
};
