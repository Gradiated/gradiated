import { describe, expect, it } from "vitest";

import {
  apiKeyExpiresAt,
  apiKeyStatus,
  firstSelectableExpiry,
} from "@/pages/api-key-status";

const NOW = new Date("2026-09-23T12:00:00.000Z");
const PAST = "2026-09-22T12:00:00.000Z";
const FUTURE = "2026-09-24T12:00:00.000Z";

describe("apiKeyStatus", () => {
  it.each([
    [{ expires_at: null, revoked_at: null }, "active"],
    [{ expires_at: FUTURE, revoked_at: null }, "active"],
    [{ expires_at: PAST, revoked_at: null }, "expired"],
    [{ expires_at: null, revoked_at: PAST }, "revoked"],
    [{ expires_at: PAST, revoked_at: PAST }, "revoked"],
  ] as const)("classifies %o as %s", (apiKey, expected) => {
    expect(apiKeyStatus(apiKey, NOW)).toBe(expected);
  });

  it("treats a key at exactly its expiry as expired", () => {
    expect(
      apiKeyStatus({ expires_at: NOW.toISOString(), revoked_at: null }, NOW),
    ).toBe("expired");
  });
});

describe("apiKeyExpiresAt", () => {
  it("ends the selected local calendar day at the end of that UTC day", () => {
    expect(apiKeyExpiresAt(new Date(2026, 9, 1))).toBe(
      "2026-10-01T23:59:59.999Z",
    );
  });
});

describe("firstSelectableExpiry", () => {
  it("returns the next local midnight", () => {
    expect(firstSelectableExpiry(new Date(2026, 8, 30, 15, 45))).toEqual(
      new Date(2026, 9, 1),
    );
  });
});
