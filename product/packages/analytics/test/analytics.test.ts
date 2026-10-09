import { describe, expect, it, vi } from "vitest";
import { createAnalytics, groupsFor } from "../src/index.js";
import { createPostHogServer } from "../src/server.js";

describe("analytics event contract", () => {
  it("attaches both groups for workspace actions and only the organization for billing", () => {
    const capture = vi.fn();
    const analytics = createAnalytics("api", capture);
    analytics.track("api_key_created", {
      organization_id: "org",
      workspace_id: "ws",
      api_key_id: "key",
      has_expiry: false,
    });
    expect(capture).toHaveBeenLastCalledWith(
      "api_key_created",
      expect.objectContaining({
        $groups: { organization: "org", workspace: "ws" },
        source: "api",
        schema_version: 1,
      }),
    );
    analytics.track("billing_checkout_started", {
      organization_id: "other-org",
      amount_nano_usd: "50000000000",
      currency: "USD",
    });
    expect(capture).toHaveBeenLastCalledWith(
      "billing_checkout_started",
      expect.objectContaining({ $groups: { organization: "other-org" } }),
    );
    expect(groupsFor({})).toEqual({});
  });

  it("rejects unknown properties and events emitted by the wrong source", () => {
    const capture = vi.fn();
    const api = createAnalytics("api", capture);
    const payload = {
      organization_id: "org",
      workspace_id: "ws",
      api_key_id: "key",
      has_expiry: false,
      secret: "must-not-leave",
    };
    expect(api.track("api_key_created", payload)).toBe(false);
    expect(
      createAnalytics("console", capture).track("api_key_created", payload),
    ).toBe(false);
    expect(api.track("sign_in_started", { method: "google" })).toBe(false);
    expect(capture).not.toHaveBeenCalled();
  });

  it("contains transport failures", () => {
    const analytics = createAnalytics("console", () => {
      throw new Error("blocked");
    });
    expect(analytics.track("sign_in_started", { method: "google" })).toBe(
      false,
    );
  });
});

describe("server PostHog delivery", () => {
  it("does not send when unconfigured", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>();
    const analytics = createPostHogServer({ fetch });
    analytics.track("user", "user_signed_in", {
      user_id: "user",
      session_id: "session",
    });
    await analytics.flush();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("retries transient failures with the same event UUID and scoped actor", async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockResolvedValueOnce(new Response(null, { status: 200 }));
    const onError = vi.fn();
    const analytics = createPostHogServer({ key: "test", fetch, onError });
    analytics.track(
      "user",
      "user_signed_up",
      { user_id: "user", organization_id: "org", workspace_id: "ws" },
      "signup-id",
    );
    await analytics.flush();
    expect(fetch).toHaveBeenCalledTimes(2);
    const payload = JSON.parse(String(fetch.mock.calls[0]![1]!.body));
    expect(payload).toMatchObject({
      distinct_id: "user",
      uuid: "signup-id",
      event: "user_signed_up",
      properties: { $groups: { organization: "org", workspace: "ws" } },
    });
    expect(fetch.mock.calls[1]![1]!.body).toBe(fetch.mock.calls[0]![1]!.body);
    expect(onError).not.toHaveBeenCalled();
  });

  it("reports permanent failure without rejecting flush", async () => {
    const fetch = vi
      .fn<typeof globalThis.fetch>()
      .mockRejectedValue(new Error("offline"));
    const onError = vi.fn();
    const analytics = createPostHogServer({ key: "test", fetch, onError });
    analytics.track("user", "user_signed_in", {
      user_id: "user",
      session_id: "session",
    });
    await expect(analytics.flush()).resolves.toBeUndefined();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(onError).toHaveBeenCalledOnce();
  });
});
