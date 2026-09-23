import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ANONYMOUS_ID = "anonymous-device";
const USER = { id: "user-1", email: "person@example.com" };

const createFakePosthog = () => {
  const enabledFlags = new Set<string>();
  const flagListeners: (() => void)[] = [];
  let distinctId = ANONYMOUS_ID;

  return {
    init: vi.fn((_key: string, config: { loaded?: () => void }) => {
      config.loaded?.();
    }),
    onFeatureFlags: vi.fn((listener: () => void) => {
      flagListeners.push(listener);

      return () => undefined;
    }),
    get_distinct_id: () => distinctId,
    identify: vi.fn((id: string) => {
      distinctId = id;
    }),
    reloadFeatureFlags: vi.fn(),
    reset: vi.fn(() => {
      distinctId = ANONYMOUS_ID;
    }),
    isFeatureEnabled: (flag: string) => enabledFlags.has(flag),
    answerFlags: (flags: string[]) => {
      enabledFlags.clear();
      for (const flag of flags) enabledFlags.add(flag);
      for (const listener of flagListeners) listener();
    },
    setDistinctId: (id: string) => {
      distinctId = id;
    },
  };
};

let posthog = createFakePosthog();

vi.mock("posthog-js", () => ({
  default: new Proxy(
    {},
    { get: (_target, property) => Reflect.get(posthog, property) },
  ),
}));

const loadFeatureFlags = async (env: Record<string, string>) => {
  for (const [name, value] of Object.entries(env)) vi.stubEnv(name, value);

  return import("@/lib/feature-flags");
};

beforeEach(() => {
  posthog = createFakePosthog();
  vi.resetModules();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.useRealTimers();
});

describe("feature flags with PostHog", () => {
  const env = { VITE_POSTHOG_KEY: "phc_test", VITE_FEATURE_FLAGS: "" };

  it("stays loading after init and ignores anonymous flag answers", async () => {
    const flags = await loadFeatureFlags(env);

    expect(flags.readFeatureFlag("training")).toBe("loading");

    posthog.answerFlags([]);

    expect(flags.readFeatureFlag("training")).toBe("loading");
  });

  it("disables the anonymous first flag load", async () => {
    await loadFeatureFlags(env);

    expect(posthog.init).toHaveBeenCalledWith(
      "phc_test",
      expect.objectContaining({
        advanced_disable_feature_flags_on_first_load: true,
      }),
    );
  });

  it("answers once flags arrive for the identified user", async () => {
    const flags = await loadFeatureFlags(env);

    flags.identifyUser(USER);

    expect(posthog.identify).toHaveBeenCalledWith(USER.id, {
      email: USER.email,
    });
    expect(flags.readFeatureFlag("training")).toBe("loading");

    posthog.answerFlags(["training"]);

    expect(flags.readFeatureFlag("training")).toBe(true);
  });

  it("cancels the fallback timer once flags arrive", async () => {
    const flags = await loadFeatureFlags(env);

    flags.identifyUser(USER);
    posthog.answerFlags(["training"]);

    expect(vi.getTimerCount()).toBe(0);
  });

  it("reads a flag missing from the answer as off", async () => {
    const flags = await loadFeatureFlags(env);

    flags.identifyUser(USER);
    posthog.answerFlags([]);

    expect(flags.readFeatureFlag("training")).toBe(false);
  });

  it("reloads flags for a returning user instead of identifying again", async () => {
    posthog.setDistinctId(USER.id);
    const flags = await loadFeatureFlags(env);

    flags.identifyUser(USER);

    expect(posthog.identify).not.toHaveBeenCalled();
    expect(posthog.reloadFeatureFlags).toHaveBeenCalledOnce();
  });

  it("reads flags as off when PostHog never answers", async () => {
    const flags = await loadFeatureFlags(env);

    flags.identifyUser(USER);
    vi.advanceTimersByTime(3_999);

    expect(flags.readFeatureFlag("training")).toBe("loading");

    vi.advanceTimersByTime(1);

    expect(flags.readFeatureFlag("training")).toBe(false);
  });

  it("returns to loading after the user is reset", async () => {
    const flags = await loadFeatureFlags(env);

    flags.identifyUser(USER);
    posthog.answerFlags(["training"]);
    flags.resetUser();

    expect(posthog.reset).toHaveBeenCalledOnce();
    expect(flags.readFeatureFlag("training")).toBe("loading");

    vi.advanceTimersByTime(10_000);

    expect(flags.readFeatureFlag("training")).toBe("loading");
  });
});

describe("feature flags without PostHog", () => {
  it("reads flags as off", async () => {
    const flags = await loadFeatureFlags({
      VITE_POSTHOG_KEY: "",
      VITE_FEATURE_FLAGS: "",
    });

    expect(flags.readFeatureFlag("training")).toBe(false);
    expect(posthog.init).not.toHaveBeenCalled();
  });

  it("turns on locally overridden flags", async () => {
    const flags = await loadFeatureFlags({
      VITE_POSTHOG_KEY: "",
      VITE_FEATURE_FLAGS: "other, training",
    });

    expect(flags.readFeatureFlag("training")).toBe(true);
  });
});
