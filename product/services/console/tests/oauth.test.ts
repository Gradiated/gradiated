import { describe, expect, it } from "vitest";

import { parseLoginSearch } from "@/lib/login-search";
import { authorizeUrl, organizationLabel } from "@/lib/oauth";

const API = "https://api.gradiated.com";

describe("authorizeUrl", () => {
  it("restarts the original authorization without the console's signature", () => {
    const url = new URL(
      authorizeUrl(
        "?response_type=code&client_id=abc&scope=mcp+offline_access&prompt=login+consent&exp=1&sig=s&ba_iat=2&ba_param=client_id",
        API,
      ),
    );

    expect(url.pathname).toBe("/api/auth/oauth2/authorize");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      response_type: "code",
      client_id: "abc",
      scope: "mcp offline_access",
      prompt: "consent",
    });
  });

  it("drops a prompt that only asked to sign in", () => {
    const url = new URL(authorizeUrl("?client_id=abc&prompt=login", API));

    expect(url.searchParams.has("prompt")).toBe(false);
  });
});

describe("parseLoginSearch", () => {
  it.each([
    ["/oauth/login?client_id=abc", { next: "/oauth/login?client_id=abc" }],
    ["/oauth/consent", { next: "/oauth/consent" }],
    ["https://evil.example/oauth/login", {}],
    ["//evil.example/oauth/login", {}],
    ["/api-keys", {}],
  ])("accepts only an OAuth page as next: %s", (next, expected) => {
    expect(parseLoginSearch({ next })).toEqual(expected);
  });
});

describe("organizationLabel", () => {
  const organizations = [
    { name: "Acme", slug: "acme" },
    { name: "Acme", slug: "acme-labs" },
    { name: "Globex", slug: "globex" },
  ];

  it("adds the slug only to names that are shared", () => {
    expect(
      organizations.map((organization) =>
        organizationLabel(organization, organizations),
      ),
    ).toEqual(["Acme (acme)", "Acme (acme-labs)", "Globex"]);
  });
});
