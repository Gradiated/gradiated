import type { Problem } from "@gradiated/contracts";
import type { Context } from "hono";
import type { ContentfulStatusCode } from "hono/utils/http-status";

export function problemResponse(
  context: Context,
  problem: Omit<Problem, "request_id">,
): Response {
  return context.json(
    problemDocument(context, problem),
    problem.status as ContentfulStatusCode,
    { "Content-Type": "application/problem+json" },
  );
}

export function problemDocument(
  context: Context,
  problem: Omit<Problem, "request_id">,
): Problem {
  return { ...problem, request_id: context.get("requestId") };
}
