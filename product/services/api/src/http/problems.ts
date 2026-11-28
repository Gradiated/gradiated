import type { Problem } from "@gradiated/contracts";
import {
  ControlServiceError,
  ModelUploadsClosedError,
  PublishError,
  TrainingAdmissionError,
  type PublishErrorCode,
} from "@gradiated/control";
import type { Context } from "hono";
import { HTTPException } from "hono/http-exception";

import { StaffSessionRecoveryRequired } from "../auth/errors.js";
import { BillingPaymentsError } from "../billing/payments.js";
import type { ApiEnvironment, SessionUser } from "../types.js";

type ProblemStatus =
  400 | 401 | 402 | 403 | 404 | 409 | 410 | 413 | 422 | 429 | 500 | 502 | 503;

export type ProblemBody = Omit<Problem, "request_id" | "status"> & {
  status: ProblemStatus;
};

const problemType = (slug: string) => `https://gradiated.com/problems/${slug}`;

export const problems = {
  payloadTooLarge: {
    type: problemType("payload-too-large"),
    title: "Payload too large",
    status: 413,
    detail: "Management API request bodies must not exceed 1 MiB.",
    code: "payload_too_large",
  },
  tooManyRequests: {
    type: problemType("too-many-requests"),
    title: "Too many requests",
    status: 429,
    detail: "Too many requests. Please retry after the indicated delay.",
    code: "rate_limited",
  },
  unauthenticated: {
    type: problemType("unauthenticated"),
    title: "Authentication required",
    status: 401,
    detail: "A valid human session is required for this operation.",
    code: "unauthenticated",
  },
  staffSessionRecovery: {
    type: problemType("staff-session-recovery-required"),
    title: "Staff session recovery required",
    status: 401,
    detail:
      "The impersonation ended. Restore the retained staff session before continuing.",
    code: "staff_session_recovery_required",
  },
  forbidden: (detail: string): ProblemBody => ({
    type: problemType("forbidden"),
    title: "Forbidden",
    status: 403,
    detail,
    code: "forbidden",
  }),
  notFound: (detail: string, title = "Not found"): ProblemBody => ({
    type: problemType("not-found"),
    title,
    status: 404,
    detail,
    code: "not_found",
  }),
  conflict: (detail: string): ProblemBody => ({
    type: problemType("conflict"),
    title: "Conflict",
    status: 409,
    detail,
    code: "conflict",
  }),
  upstreamFailed: (detail: string): ProblemBody => ({
    type: problemType("upstream-failed"),
    title: "Upstream server failed",
    status: 502,
    detail,
    code: "upstream_failed",
  }),
  unavailable: (detail: string): ProblemBody => ({
    type: problemType("unavailable"),
    title: "Service unavailable",
    status: 503,
    detail,
    code: "unavailable",
  }),
  onboardingConflict: (
    code:
      | "nda_required"
      | "slack_channel_name_taken"
      | "slack_channel_required"
      | "github_authorization_required"
      | "github_installation_unverified"
      | "github_repositories_required"
      | "submission_in_progress",
    detail: string,
  ): ProblemBody => ({
    type: problemType(code.replaceAll("_", "-")),
    title: "Engineer onboarding step incomplete",
    status: 409,
    detail,
    code,
  }),
  slackInvitationCooldown: (detail: string): ProblemBody => ({
    type: problemType("slack-invitation-cooldown"),
    title: "Slack invitation recently sent",
    status: 429,
    detail,
    code: "slack_invitation_cooldown",
  }),
  notPrepaid: (detail: string): ProblemBody => ({
    type: problemType("not-prepaid"),
    title: "Prepaid billing required",
    status: 409,
    detail,
    code: "not_prepaid",
  }),
  billingConflict: (
    code: "card_not_confirmed" | "no_billing_customer",
    detail: string,
  ): ProblemBody => ({
    type: problemType(code.replaceAll("_", "-")),
    title:
      code === "card_not_confirmed"
        ? "Card not confirmed"
        : "No billing history",
    status: 409,
    detail,
    code,
  }),
  paymentFailed: (detail: string): ProblemBody => ({
    type: problemType("payment-failed"),
    title: "Payment failed",
    status: 402,
    detail,
    code: "payment_failed",
  }),
  billingProviderUnavailable: (
    code: "provider_error" | "unavailable",
    detail: string,
  ): ProblemBody => ({
    type: problemType("billing-provider-unavailable"),
    title: "Billing provider unavailable",
    status: 503,
    detail,
    code,
  }),
  invalidStripeWebhook: (detail: string): ProblemBody => ({
    type: problemType("invalid-stripe-webhook"),
    title: "Invalid Stripe webhook",
    status: 400,
    detail,
    code: "invalid_webhook",
  }),
  notReady: {
    type: problemType("not-ready"),
    title: "Service not ready",
    status: 503,
    detail:
      "At least one dependency required for product traffic is unavailable.",
    code: "not_ready",
  },
  internal: {
    type: problemType("internal"),
    title: "Internal server error",
    status: 500,
    detail: "The server could not complete the request.",
    code: "internal_error",
  },
  validation: (errors: NonNullable<Problem["errors"]>): ProblemBody => ({
    type: problemType("validation"),
    title: "Request validation failed",
    status: 422,
    detail: "The request does not match the operation contract.",
    code: "validation_failed",
    errors,
  }),
} satisfies Record<string, ProblemBody | ((...args: never[]) => ProblemBody)>;

const PUBLISH_CONFLICTS = new Set<PublishErrorCode>([
  "artifact_checksum_mismatch",
  "model_base_mismatch",
  "version_name_taken",
  "version_in_production",
]);

export class ApiProblem extends Error {
  constructor(
    readonly problem: ProblemBody,
    override readonly cause?: unknown,
  ) {
    super(problem.title);
    this.name = "ApiProblem";
  }
}

const controlProblem = (error: ControlServiceError): ApiProblem => {
  switch (error.code) {
    case "forbidden":
      return new ApiProblem(problems.forbidden(error.message), error.cause);
    case "not_found":
      return new ApiProblem(problems.notFound(error.message), error.cause);
    case "conflict":
      return new ApiProblem(problems.conflict(error.message), error.cause);
    case "unavailable":
      return new ApiProblem(problems.unavailable(error.message), error.cause);
  }
};

const billingProblem = (error: BillingPaymentsError): ApiProblem => {
  switch (error.code) {
    case "invalid_webhook":
      return new ApiProblem(
        problems.invalidStripeWebhook(error.message),
        error.cause,
      );
    case "not_prepaid":
      return new ApiProblem(problems.notPrepaid(error.message), error.cause);
    case "card_not_confirmed":
    case "no_billing_customer":
      return new ApiProblem(
        problems.billingConflict(error.code, error.message),
        error.cause,
      );
    case "payment_failed":
      return new ApiProblem(problems.paymentFailed(error.message), error.cause);
    case "provider_error":
    case "unavailable":
      return new ApiProblem(
        problems.billingProviderUnavailable(error.code, error.message),
        error.cause,
      );
  }
};

export const toApiProblem = (error: unknown): ApiProblem | undefined => {
  if (error instanceof ApiProblem) return error;
  if (error instanceof TrainingAdmissionError)
    return new ApiProblem({
      type: problemType(error.code),
      title: "Training cannot start",
      status: error.code === "already_training" ? 409 : 422,
      code: error.code,
      detail: error.message,
    });
  if (error instanceof ModelUploadsClosedError)
    return new ApiProblem({
      type: problemType("use-grad-artifacts-upload"),
      title: "Model uploads moved to grad",
      status: 410,
      code: error.code,
      detail: error.message,
    });
  if (error instanceof PublishError)
    return new ApiProblem({
      type: problemType(error.code.replaceAll("_", "-")),
      title: "The artifact cannot be published",
      status: PUBLISH_CONFLICTS.has(error.code) ? 409 : 422,
      code: error.code,
      detail: error.message,
    });
  if (error instanceof ControlServiceError) return controlProblem(error);
  if (error instanceof BillingPaymentsError) return billingProblem(error);
  if (error instanceof HTTPException && error.status === 400) {
    return new ApiProblem(
      problems.validation([
        { path: "", message: "The request body is malformed." },
      ]),
      error,
    );
  }

  return undefined;
};

export const requireUser = async (context: {
  get(key: "resolveUser"): () => Promise<SessionUser | null>;
}): Promise<SessionUser> => {
  let user: SessionUser | null;
  try {
    user = await context.get("resolveUser")();
  } catch (error) {
    if (error instanceof StaffSessionRecoveryRequired)
      throw new ApiProblem(problems.staffSessionRecovery);

    throw new ApiProblem(
      problems.unavailable("The session store is unavailable."),
      error,
    );
  }

  if (!user) throw new ApiProblem(problems.unauthenticated);

  return user;
};

export const problemResponse = <Status extends ProblemStatus>(
  context: Context<ApiEnvironment>,
  problem: ProblemBody & { status: Status },
) =>
  context.json(
    { ...problem, request_id: context.get("requestId") },
    problem.status,
    { "Content-Type": "application/problem+json" },
  );
