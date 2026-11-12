import { describe, expect, it } from "vitest";

import {
  organizationSlugError,
  privateModelName,
  slugFromName,
} from "@/lib/model-name";

describe("privateModelName", () => {
  it("names the production version by organization and task", () => {
    expect(privateModelName("acme", "support-triage")).toBe(
      "acme/support-triage",
    );
  });

  it("names an exact version by organization, task and version", () => {
    expect(privateModelName("acme", "support-triage", "2026-11-12-2")).toBe(
      "acme/support-triage/2026-11-12-2",
    );
  });
});

describe("organizationSlugError", () => {
  it.each(["ab", "acme", "acme-labs-2", "a".repeat(39)])(
    "accepts %j",
    (value) => {
      expect(organizationSlugError(value)).toBeNull();
    },
  );

  it("asks for a slug when empty", () => {
    expect(organizationSlugError("")).toBe("Enter a slug.");
  });

  it.each(["a", "-acme", "acme-", "Acme", "acme_labs", "a".repeat(40)])(
    "rejects %j",
    (value) => {
      expect(organizationSlugError(value)).toMatch(/^Use 2 to 39/);
    },
  );
});

describe("slugFromName", () => {
  it.each([
    ["Acme", "acme"],
    ["  Acme Labs, Inc. ", "acme-labs-inc"],
    ["Café Ünïcode", "cafe-unicode"],
    ["株式会社", ""],
    ["a".repeat(38) + " b", "a".repeat(38)],
  ])("slugifies %j", (name, slug) => {
    expect(slugFromName(name)).toBe(slug);
  });
});
