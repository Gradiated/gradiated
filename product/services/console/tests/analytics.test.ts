import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const posthog = {
  init: vi.fn(),
  capture: vi.fn(),
  group: vi.fn(),
  resetGroups: vi.fn(),
};
vi.mock("posthog-js", () => ({ default: posthog }));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  vi.stubEnv("VITE_POSTHOG_KEY", "test");
});
afterEach(() => vi.unstubAllEnvs());

describe("console analytics", () => {
  it("uses SDK pageviews with console attribution and sanitized URL paths", async () => {
    await import("@/lib/posthog");
    const options = posthog.init.mock.calls[0]![1];
    expect(options.capture_pageview).toBe("history_change");

    const event = options.before_send({
      event: "$pageview",
      $set_once: {
        $initial_current_url:
          "https://console.gradiated.com/login?token=private#secret",
      },
      properties: {
        $current_url:
          "https://console.gradiated.com/login?token=private#secret",
        $pathname: "/login",
        $session_entry_url:
          "https://console.gradiated.com/login?token=private#secret",
      },
    });
    expect(event.properties).toMatchObject({
      source: "console",
      schema_version: 1,
      $current_url: "https://console.gradiated.com/login",
      $pathname: "/login",
      $session_entry_url: "https://console.gradiated.com/login",
    });
    expect(event.$set_once.$initial_current_url).toBe(
      "https://console.gradiated.com/login",
    );
    expect(JSON.stringify(event)).not.toMatch(/private|secret/);
  });

  it("removes inherited workspace groups and URLs at the final SDK send boundary", async () => {
    await import("@/lib/analytics");
    const options = posthog.init.mock.calls[0]![1];
    const event = options.before_send({
      event: "billing_top_up_clicked",
      $set_once: {
        $initial_current_url:
          "https://console.gradiated.com/login?token=private",
      },
      properties: {
        organization_id: "org-2",
        $groups: { organization: "org-1", workspace: "ws-1" },
        $current_url: "https://console.gradiated.com/login?token=private",
        $session_entry_url: "https://console.gradiated.com/login?token=private",
        $set_once: {
          $initial_current_url:
            "https://console.gradiated.com/login?token=private",
        },
      },
    });
    expect(event.properties.$groups).toEqual({ organization: "org-2" });
    expect(JSON.stringify(event)).not.toContain("token=private");
  });
  it("updates both groups when workspace or organization changes without repeating identical updates", async () => {
    const analytics = await import("@/lib/analytics");
    analytics.setAnalyticsScope("user", "org-1", "ws-1", true);
    analytics.setAnalyticsScope("user", "org-1", "ws-1", true);
    expect(posthog.resetGroups).toHaveBeenCalledOnce();
    analytics.setAnalyticsScope("user", "org-2", "ws-2", false);
    expect(posthog.resetGroups).toHaveBeenCalledTimes(2);
    expect(posthog.group).toHaveBeenLastCalledWith("workspace", "ws-2", {
      organization_id: "org-2",
      is_default: false,
    });
  });

  it("uses the event scope even when a different workspace is active", async () => {
    const { analytics, setAnalyticsScope } = await import("@/lib/analytics");
    setAnalyticsScope("user", "org-1", "ws-1", false);
    analytics.track("workspace_selected", {
      organization_id: "org-2",
      workspace_id: "ws-2",
    });
    expect(posthog.capture).toHaveBeenCalledWith(
      "workspace_selected",
      expect.objectContaining({
        $groups: { organization: "org-2", workspace: "ws-2" },
      }),
    );
    analytics.track("billing_top_up_clicked", { organization_id: "org-2" });
    expect(posthog.capture).toHaveBeenLastCalledWith(
      "billing_top_up_clicked",
      expect.objectContaining({ $groups: { organization: "org-2" } }),
    );
  });

  it("does not send business events from the browser", async () => {
    const { analytics } = await import("@/lib/analytics");
    expect(
      analytics.track("workspace_created", {
        organization_id: "org",
        workspace_id: "ws",
        is_default: false,
      }),
    ).toBe(false);
    expect(posthog.capture).not.toHaveBeenCalled();
  });

  it("reassociates the same scope after logout", async () => {
    const { setAnalyticsScope, clearAnalyticsScope } =
      await import("@/lib/analytics");
    setAnalyticsScope("user", "org", "ws", true);
    clearAnalyticsScope();
    setAnalyticsScope("user", "org", "ws", true);
    expect(posthog.resetGroups).toHaveBeenCalledTimes(2);
  });

  it("is disabled without a project key", async () => {
    vi.stubEnv("VITE_POSTHOG_KEY", "");
    const { analytics, setAnalyticsScope } = await import("@/lib/analytics");
    analytics.track("sign_in_started", { method: "google" });
    setAnalyticsScope("user", "org", "ws", true);
    expect(posthog.init).not.toHaveBeenCalled();
    expect(posthog.capture).not.toHaveBeenCalled();
    expect(posthog.group).not.toHaveBeenCalled();
  });
});
