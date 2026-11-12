import { describe, expect, it } from "vitest";
import {
  loginSearchFor,
  parseOnboardingSearch,
  signInCallbacks,
} from "@/lib/engineer-onboarding";
import { parseLoginSearch } from "@/lib/login-search";

const origin = "https://console.gradiated.com";

describe("post-training onboarding journey", () => {
  it("preserves a valid organization selection and drops invalid IDs", () => {
    const organization = "0198ae59-294a-73a9-9d2f-962449d34226";
    expect(
      parseOnboardingSearch({ journey: "post-training", organization }),
    ).toEqual({ journey: "post-training", organization });
    expect(
      parseOnboardingSearch({
        journey: "post-training",
        organization: "https://example.com",
      }),
    ).toEqual({ journey: "post-training" });
  });

  it("keeps a console path to return to and drops anything else", () => {
    expect(
      parseOnboardingSearch({ journey: "post-training", from: "/tasks?tab=1" }),
    ).toEqual({ journey: "post-training", from: "/tasks?tab=1" });
    for (const from of [
      "https://evil.example/tasks",
      "//evil.example/tasks",
      "/\\evil.example",
      "tasks",
      "/onboarding?journey=post-training",
      "/" + "a".repeat(600),
    ])
      expect(parseOnboardingSearch({ from })).toEqual({});
  });

  it("only accepts the known journey", () => {
    expect(parseLoginSearch({ journey: "post-training" })).toEqual({
      journey: "post-training",
    });
    for (const journey of [
      "https://evil.example",
      "//evil.example",
      "engineer",
      "post-training?url=evil",
    ]) {
      expect(parseLoginSearch({ journey })).toEqual({});
      expect(parseOnboardingSearch({ journey })).toEqual({});
    }
  });

  it("returns every post-training sign-in to the journey", () => {
    expect(signInCallbacks({ journey: "post-training" }, origin)).toEqual({
      callbackURL: `${origin}/onboarding?journey=post-training`,
      newUserCallbackURL: `${origin}/onboarding?journey=post-training`,
      errorCallbackURL: `${origin}/login?journey=post-training`,
    });
  });

  it("keeps invitation acceptance ahead of the journey", () => {
    const invitation = "A".repeat(43);
    const callbacks = signInCallbacks(
      { invitation, journey: "post-training" },
      origin,
    );
    expect(callbacks.callbackURL).toBe(
      `${origin}/invitations/accept?token=${invitation}`,
    );
    expect(callbacks.newUserCallbackURL).toBe(callbacks.callbackURL);
  });

  it("preserves the standard sign-in and signup destinations", () => {
    expect(signInCallbacks({}, origin)).toEqual({
      callbackURL: `${origin}/api-keys`,
      newUserCallbackURL: `${origin}/onboarding`,
      errorCallbackURL: `${origin}/login`,
    });
  });

  it("returns an expired session on the journey to its sign-in", () => {
    expect(
      loginSearchFor({
        pathname: "/onboarding",
        search: { journey: "post-training" },
      }),
    ).toEqual({ journey: "post-training" });
    expect(loginSearchFor({ pathname: "/onboarding", search: {} })).toEqual({});
    expect(
      loginSearchFor({
        pathname: "/api-keys",
        search: { journey: "post-training" },
      }),
    ).toEqual({});
  });
});
