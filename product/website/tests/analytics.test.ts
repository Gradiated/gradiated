import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const posthog = { init: vi.fn() };
vi.mock("posthog-js", () => ({ default: posthog }));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  vi.stubEnv("PROD", true);
  vi.stubEnv("VITE_POSTHOG_KEY", "");
  vi.stubEnv("VITE_POSTHOG_HOST", "");
  vi.stubGlobal("window", { location: { hostname: "www.gradiated.com" } });
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("website analytics", () => {
  it("tracks visits and SPA navigation in the production project", async () => {
    await import("../src/analytics");

    expect(posthog.init).toHaveBeenCalledWith(
      "phc_m2sik8V9cUpSGFmprudSHQwQm96YbvoNYobyBA4YqHoW",
      expect.objectContaining({
        api_host: "https://us.i.posthog.com",
        capture_pageview: "history_change",
        autocapture: false,
        disable_session_recording: true,
      }),
    );
  });

  it.each(["localhost", "gradiated-preview.vercel.app"])(
    "keeps %s traffic out of the production project",
    async (hostname) => {
      vi.stubGlobal("window", { location: { hostname } });
      await import("../src/analytics");

      expect(posthog.init).not.toHaveBeenCalled();
    },
  );

  it("keeps development builds off even on a production hostname", async () => {
    vi.stubEnv("PROD", false);
    await import("../src/analytics");

    expect(posthog.init).not.toHaveBeenCalled();
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
