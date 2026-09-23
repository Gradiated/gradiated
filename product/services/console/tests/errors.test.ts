import { describe, expect, it } from "vitest";

import { errorMessage, httpStatus, isClientError } from "@/lib/errors";

const requestError = (status: unknown) =>
  Object.assign(new Error("request failed"), { status });

describe("httpStatus", () => {
  it("reads a numeric status", () => {
    expect(httpStatus(requestError(401))).toBe(401);
  });

  it.each([
    ["an error without a status", new Error("boom")],
    ["a non-numeric status", requestError("401")],
    ["a non-object", "boom"],
    ["null", null],
  ])("is undefined for %s", (_, error) => {
    expect(httpStatus(error)).toBeUndefined();
  });
});

describe("isClientError", () => {
  it.each([
    [400, true],
    [401, true],
    [499, true],
    [399, false],
    [500, false],
    [503, false],
  ])("status %d is a client error: %s", (status, expected) => {
    expect(isClientError(requestError(status))).toBe(expected);
  });

  it("is false without a status", () => {
    expect(isClientError(new Error("network down"))).toBe(false);
  });
});

describe("errorMessage", () => {
  it("uses the error message", () => {
    expect(errorMessage(new Error("boom"), "fallback")).toBe("boom");
  });

  it.each([new Error(""), "boom", undefined])("falls back for %j", (error) => {
    expect(errorMessage(error, "fallback")).toBe("fallback");
  });
});
