import { afterEach, describe, expect, it, vi } from "vitest";

import {
  callbackErrorCode,
  logSignInCallbackFailure,
  logSignInFailure,
  signInFailureCode,
} from "@/pages/sign-in-failure";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("signInFailureCode", () => {
  it("uses the name of a thrown error, never its message", () => {
    expect(signInFailureCode(new TypeError("secret detail"))).toBe("TypeError");
  });

  it("prefers the code of a returned auth error", () => {
    expect(
      signInFailureCode({ code: "RATE_LIMITED", status: 429, message: "x" }),
    ).toBe("RATE_LIMITED");
  });

  it("falls back to the status when the code is missing or unbounded", () => {
    expect(signInFailureCode({ status: 500 })).toBe("http_500");
    expect(signInFailureCode({ code: "not a code", status: 400 })).toBe(
      "http_400",
    );
  });

  it("names non-object failures by type", () => {
    expect(signInFailureCode("boom")).toBe("string");
    expect(signInFailureCode(null)).toBe("object");
    expect(signInFailureCode({})).toBe("unknown");
  });
});

describe("callbackErrorCode", () => {
  it("keeps a bounded provider code and replaces anything else", () => {
    expect(callbackErrorCode("unable_to_get_user_info")).toBe(
      "unable_to_get_user_info",
    );
    expect(callbackErrorCode("<script>")).toBe("unrecognized");
    expect(callbackErrorCode("a".repeat(65))).toBe("unrecognized");
  });
});

describe("logging", () => {
  it("logs the method and code of a failed sign-in", () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});

    logSignInFailure("google", { code: "PROVIDER_NOT_FOUND", status: 404 });
    logSignInCallbackFailure("access_denied");

    expect(log.mock.calls).toEqual([
      ["sign_in_failed", "google", "PROVIDER_NOT_FOUND"],
      ["sign_in_callback_failed", "access_denied"],
    ]);
  });
});
