import { describe, expect, it } from "vitest";

import { ApiError, requireData, requireOk } from "@/api/client";
import { httpStatus } from "@/lib/errors";

const problem = {
  type: "https://gradiated.com/problems/unauthenticated",
  title: "Unauthenticated",
  status: 401,
  detail: "Sign in again.",
  code: "unauthenticated",
  request_id: "req_123",
};

const result = <T>(status: number, data?: T, error?: unknown) =>
  Promise.resolve({ data, error, response: new Response(null, { status }) });

const rejection = async (request: Promise<unknown>): Promise<unknown> => {
  try {
    await request;
  } catch (error) {
    return error;
  }

  throw new Error("Expected the request to fail");
};

describe("requireData", () => {
  it("returns the data of a successful response", async () => {
    await expect(requireData(result(200, { id: "model" }))).resolves.toEqual({
      id: "model",
    });
  });

  it("builds an ApiError from a Problem body", async () => {
    const error = await rejection(requireData(result(401, undefined, problem)));

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      message: "Sign in again.",
      status: 401,
      code: "unauthenticated",
      requestId: "req_123",
    });
  });

  it("falls back to the status when the body is not a Problem", async () => {
    const error = await rejection(
      requireData(result(502, undefined, "Bad gateway")),
    );

    expect(error).toMatchObject({
      message: "Request failed with status 502",
      status: 502,
      code: undefined,
      requestId: undefined,
    });
  });

  it("keeps the detail of a partial Problem body", async () => {
    const error = await rejection(
      requireData(result(502, undefined, { detail: "Stripe is unavailable." })),
    );

    expect(error).toMatchObject({
      message: "Stripe is unavailable.",
      status: 502,
      code: undefined,
      requestId: undefined,
    });
  });

  it("ignores Problem fields that are not strings", async () => {
    const error = await rejection(
      requireData(result(500, undefined, { ...problem, request_id: 7 })),
    );

    expect(error).toMatchObject({
      message: "Sign in again.",
      code: "unauthenticated",
      requestId: undefined,
    });
  });
});

describe("requireOk", () => {
  it("resolves for a response without a body", async () => {
    await expect(requireOk(result(204))).resolves.toBeUndefined();
  });

  it("keeps the HTTP status of a failed response", async () => {
    const error = await rejection(requireOk(result(401, undefined, problem)));

    expect(httpStatus(error)).toBe(401);
    expect(error).toMatchObject({ message: "Sign in again." });
  });
});
