import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const posthog = { init: vi.fn() };
vi.mock("posthog-js", () => ({ default: posthog }));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  vi.stubEnv("PROD", true);
  vi.stubEnv("VITE_POSTHOG_KEY", "configured-test-project");
  vi.stubEnv("VITE_POSTHOG_HOST", "");
  vi.stubGlobal("window", { location: { hostname: "www.gradiated.com" } });
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("website analytics", () => {
  it("allows recording snapshots without overriding project replay settings", async () => {
    await import("../src/analytics");
    const options = posthog.init.mock.calls[0]![1];
    const snapshots = [{ type: 2, data: { node: { type: 0 } } }];
    const event = options.before_send({
      event: "$snapshot",
      properties: { $snapshot_data: snapshots, $session_id: "test-session" },
    });

    expect(options).not.toHaveProperty("disable_session_recording");
    expect(options.advanced_disable_feature_flags).not.toBe(true);
    expect(event.properties.$snapshot_data).toEqual(snapshots);
    expect(event.properties.$session_id).toBe("test-session");
    expect(options).not.toHaveProperty("session_recording");
    expect(options).not.toHaveProperty("enable_recording_console_log");
    expect(event.properties.source).toBe("website");
    expect(
      options.before_send({ event: "$autocapture", properties: {} }),
    ).toBeNull();
  });

  it("tracks visits and SPA navigation in the production project", async () => {
    await import("../src/analytics");

    expect(posthog.init).toHaveBeenCalledWith(
      "configured-test-project",
      expect.objectContaining({
        api_host: "https://us.i.posthog.com",
        capture_pageview: "history_change",
        autocapture: false,
        advanced_disable_feature_flags_on_first_load: true,
      }),
    );
  });

  it.each(["localhost", "gradiated-preview.vercel.app"])(
    "keeps %s traffic out of the production project",
    async (hostname) => {
      vi.stubEnv("VITE_POSTHOG_KEY", "");
      vi.stubGlobal("window", { location: { hostname } });
      await import("../src/analytics");

      expect(posthog.init).not.toHaveBeenCalled();
    },
  );

  it("keeps development builds off even on a production hostname", async () => {
    vi.stubEnv("PROD", false);
    vi.stubEnv("VITE_POSTHOG_KEY", "");
    await import("../src/analytics");

    expect(posthog.init).not.toHaveBeenCalled();
  });

  it("does not initialize on production domains without deployment configuration", async () => {
    vi.stubEnv("VITE_POSTHOG_KEY", "");
    await import("../src/analytics");

    expect(posthog.init).not.toHaveBeenCalled();
  });

  it("preserves direct referrer attribution on events and persons", async () => {
    await import("../src/analytics");
    const options = posthog.init.mock.calls[0]![1];
    // posthog-js only attaches $referrer and $referring_domain when it saves referrer info.
    expect(options.save_referrer).not.toBe(false);
    const event = options.before_send({
      event: "$pageview",
      $set_once: { $initial_referrer: "$direct" },
      $set: { $session_entry_referrer: "$direct" },
      properties: {
        $referrer: "$direct",
        $set_once: { $initial_referrer: "$direct" },
        $set: { $session_entry_referrer: "$direct" },
      },
    });

    expect(event.properties.$referrer).toBe("$direct");
    expect(event.properties.$set_once.$initial_referrer).toBe("$direct");
    expect(event.properties.$set.$session_entry_referrer).toBe("$direct");
    expect(event.$set_once.$initial_referrer).toBe("$direct");
    expect(event.$set.$session_entry_referrer).toBe("$direct");
  });

  it("allows a separate development project and ingestion host", async () => {
    vi.stubEnv("PROD", false);
    vi.stubEnv("VITE_POSTHOG_KEY", "development-project");
    vi.stubEnv("VITE_POSTHOG_HOST", "https://eu.i.posthog.com");
    await import("../src/analytics");

    expect(posthog.init).toHaveBeenCalledWith(
      "development-project",
      expect.objectContaining({ api_host: "https://eu.i.posthog.com" }),
    );
  });

  it("removes query and fragment secrets from event and person URLs", async () => {
    await import("../src/analytics");
    const options = posthog.init.mock.calls[0]![1];
    const event = options.before_send({
      event: "$pageview",
      $set_once: {
        $initial_current_url: "https://www.gradiated.com/?token=private",
      },
      $set: { $session_entry_url: "https://www.gradiated.com/#secret" },
      properties: {
        $current_url: "https://www.gradiated.com/docs/?token=private#secret",
        $referrer: "https://console.gradiated.com/login?token=private",
        $set_once: {
          $initial_current_url: "https://www.gradiated.com/?token=private",
          $initial_referrer: "invalid?token=private",
        },
        $set: { $session_entry_url: "https://www.gradiated.com/#secret" },
      },
    });

    expect(event.properties).toMatchObject({
      source: "website",
      schema_version: 1,
      $current_url: "https://www.gradiated.com/docs/",
    });
    expect(JSON.stringify(event)).not.toMatch(/private|secret/);
    expect(
      options.before_send({ event: "$autocapture", properties: {} }),
    ).toBeNull();
  });
});
