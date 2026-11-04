import { describe, expect, it } from "vitest";
import {
  engineerOnboardingUrl,
  parseOnboardingSearch,
  signInCallbacks,
} from "@/lib/engineer-onboarding";
import { parseLoginSearch } from "@/lib/login-search";

describe("post-account engineer onboarding", () => {
  it("preserves a valid organization selection and drops invalid IDs", () => {
    const organization = "0198ae59-294a-73a9-9d2f-962449d34226";
    expect(parseOnboardingSearch({ next: "engineer", organization })).toEqual({
      next: "engineer",
      organization,
    });
    expect(
      parseOnboardingSearch({
        next: "engineer",
        organization: "https://example.com",
      }),
    ).toEqual({ next: "engineer" });
  });
  it("only accepts the fixed engineer destination", () => {
    expect(parseLoginSearch({ next: "engineer" })).toEqual({
      next: "engineer",
    });
    expect(parseOnboardingSearch({ next: "engineer" })).toEqual({
      next: "engineer",
    });
    for (const next of [
      "https://evil.example",
      "//evil.example",
      "/get-started/",
      "engineer?url=evil",
    ]) {
      expect(parseLoginSearch({ next })).toEqual({});
      expect(parseOnboardingSearch({ next })).toEqual({});
    }
  });

  it("routes a new engineer customer through existing organization setup", () => {
    const callbacks = signInCallbacks(
      { next: "engineer" },
      "https://console.gradiated.com",
    );
    expect(callbacks.newUserCallbackURL).toBe(
      "https://console.gradiated.com/onboarding?next=engineer",
    );
    expect(new URL(callbacks.callbackURL).pathname).toBe("/get-started/");
    expect(callbacks.errorCallbackURL).toBe(
      "https://console.gradiated.com/login?next=engineer",
    );
  });

  it("keeps invitation acceptance ahead of engineer onboarding", () => {
    const invitation = "A".repeat(43);
    const callbacks = signInCallbacks(
      { invitation, next: "engineer" },
      "https://console.gradiated.com",
    );
    expect(callbacks.callbackURL).toBe(
      "https://console.gradiated.com/invitations/accept?token=" + invitation,
    );
    expect(callbacks.newUserCallbackURL).toBe(callbacks.callbackURL);
  });

  it("preserves the standard sign-in and signup destinations", () => {
    expect(signInCallbacks({}, "https://console.gradiated.com")).toEqual({
      callbackURL: "https://console.gradiated.com/api-keys",
      newUserCallbackURL: "https://console.gradiated.com/onboarding",
      errorCallbackURL: "https://console.gradiated.com/login",
    });
  });

  it("returns the newly created organization without putting identity details in the URL", () => {
    const url = new URL(
      engineerOnboardingUrl("organization-id", "https://gradiated.com"),
    );
    expect(url.pathname).toBe("/get-started/");
    expect([...url.searchParams]).toEqual([
      ["organization", "organization-id"],
    ]);
  });
});
