import { describe, expect, it } from "vitest";

import { companyEmailDomain } from "../src/organizations/email-domains.js";

describe("company email domains", () => {
  it.each([
    ["alex@Acme.COM", "acme.com"],
    ["alex@eng.acme.co.uk", "eng.acme.co.uk"],
  ])("accepts the verified company address %s", (email, domain) => {
    expect(companyEmailDomain({ email, emailVerified: true })).toBe(domain);
  });

  it.each([
    "alex@gmail.com",
    "alex@outlook.com",
    "alex@icloud.com",
    "alex@proton.me",
    "alex@hey.com",
    "alex@mailinator.com",
    "alex@localhost",
    "x@@acme.com",
  ])("rejects the personal or disposable address %s", (email) => {
    expect(companyEmailDomain({ email, emailVerified: true })).toBeNull();
  });

  it("rejects unverified addresses", () => {
    expect(
      companyEmailDomain({ email: "alex@acme.com", emailVerified: false }),
    ).toBeNull();
  });
});
