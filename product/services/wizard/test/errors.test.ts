import { describe, expect, it } from "vitest";
import { failureMessage, requestFailure, WizardError } from "../src/errors.js";
import { HttpStatusError, NetworkError } from "../src/http.js";

const systemError = (code: string): Error =>
  Object.assign(new Error(`${code}: operation failed`), { code });

const wrapped = (cause: unknown): WizardError =>
  new WizardError("Could not finish.", { cause });

describe("failureMessage", () => {
  it.each([
    [
      "the problem code",
      new HttpStatusError(503, "unavailable", "Down."),
      "unavailable",
    ],
    [
      "the HTTP status without a problem code",
      new HttpStatusError(502, undefined, "Bad gateway."),
      "http_502",
    ],
    [
      "a network timeout",
      new NetworkError("timeout", { cause: undefined }),
      "network_timeout",
    ],
    [
      "a network failure",
      new NetworkError("failure", { cause: undefined }),
      "network_failure",
    ],
    ["a missing file", systemError("ENOENT"), "ENOENT"],
    ["a permission error", systemError("EACCES"), "EACCES"],
  ])("appends %s from a wizard error cause", (_case, cause, code) => {
    expect(failureMessage(wrapped(cause))).toBe(`Could not finish. (${code})`);
  });

  it("keeps a wizard error without a diagnostic cause unchanged", () => {
    expect(failureMessage(new WizardError("No key."))).toBe("No key.");
    expect(failureMessage(wrapped(new Error("hidden")))).toBe(
      "Could not finish.",
    );
  });

  it("appends the code of a plain error itself", () => {
    expect(
      failureMessage(new HttpStatusError(500, undefined, "Server error.")),
    ).toBe("HTTP 500: Server error. (http_500)");
    expect(failureMessage(systemError("EACCES"))).toBe(
      "EACCES: operation failed (EACCES)",
    );
    expect(failureMessage(new Error("Broken."))).toBe("Broken.");
  });

  it("does not print a value that is not an error", () => {
    expect(failureMessage("grad_secret")).toBe("Unexpected failure.");
  });
});

describe("requestFailure", () => {
  it("names the failed action for an HTTP status", () => {
    const cause = new HttpStatusError(503, "unavailable", "Down.");
    const error = requestFailure("Could not send the code", cause);

    expect(error).toEqual(
      new WizardError("Could not send the code (503): Down."),
    );
    expect(error).toHaveProperty("cause", cause);
  });

  it("names the failed action for a network error", () => {
    const cause = new NetworkError("timeout", { cause: undefined });
    const error = requestFailure("Could not send the code", cause);

    expect(error).toEqual(
      new WizardError("Could not send the code: The request timed out."),
    );
    expect(error).toHaveProperty("cause", cause);
  });

  it("returns any other error unchanged", () => {
    const cause = new WizardError("Already explained.");

    expect(requestFailure("Could not send the code", cause)).toBe(cause);
  });
});
