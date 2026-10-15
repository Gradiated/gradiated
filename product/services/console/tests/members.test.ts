import { describe, expect, it } from "vitest";

import { parseEmails } from "@/lib/emails";
import { parseLoginSearch } from "@/lib/login-search";

describe("invitation input", () => {
  it("splits, normalizes and de-duplicates addresses", () => {
    expect(
      parseEmails(" Morgan@Acme.com,casey@acme.com\nmorgan@acme.com; nope "),
    ).toEqual({
      emails: ["morgan@acme.com", "casey@acme.com"],
      invalid: ["nope"],
    });
    expect(parseEmails("   ")).toEqual({ emails: [], invalid: [] });
  });
});

describe("login search", () => {
  it("keeps only well-formed invitation tokens", () => {
    const token = "a".repeat(43);

    expect(parseLoginSearch({ invitation: token })).toEqual({
      invitation: token,
    });
    for (const invitation of ["short", "//evil.example", 7])
      expect(parseLoginSearch({ invitation })).toEqual({});
  });
});
