import posthog from "posthog-js";
import { useEffect, useState } from "react";

/**
 * Feature flags come from PostHog when `VITE_POSTHOG_KEY` is set at build time.
 * Without a key nothing is initialised and every flag is off, except flags named
 * in `VITE_FEATURE_FLAGS` (comma-separated), which is the local-development override.
 *
 * Flags this console reads:
 * - `training`: the Training pages (a client-side mock today). Rolled out
 *   by person property `email` in PostHog, e.g. "ends with @gradiated.com".
 */
export type FeatureFlag = "training";

const localOverrides = new Set(
  (import.meta.env.VITE_FEATURE_FLAGS ?? "")
    .split(",")
    .map((flag: string) => flag.trim())
    .filter(Boolean),
);

const key = import.meta.env.VITE_POSTHOG_KEY as string | undefined;
const enabled = Boolean(key);
let flagsLoaded = false;
const listeners = new Set<() => void>();

if (enabled) {
  posthog.init(key!, {
    api_host: import.meta.env.VITE_POSTHOG_HOST ?? "https://us.i.posthog.com",
    person_profiles: "identified_only",
    capture_pageview: false,
    autocapture: false,
    loaded: () => {
      flagsLoaded = true;
      for (const listener of listeners) listener();
    },
  });
  posthog.onFeatureFlags(() => {
    flagsLoaded = true;
    for (const listener of listeners) listener();
  });
  // A blocked or failed flag request must not leave gated pages blank: after this, flags read as off.
  window.setTimeout(() => {
    if (flagsLoaded) return;
    flagsLoaded = true;
    for (const listener of listeners) listener();
  }, 4000);
}

/** Ties flag evaluation to the signed-in user so per-person rollouts apply. */
export const identifyUser = (user: { id: string; email: string }) => {
  if (!enabled) return;
  if (posthog.get_distinct_id() === user.id) return;
  posthog.identify(user.id, { email: user.email });
};

export const resetUser = () => {
  if (enabled) posthog.reset();
};

const read = (flag: FeatureFlag): boolean | "loading" => {
  if (localOverrides.has(flag)) return true;
  if (!enabled) return false;
  if (!flagsLoaded) return "loading";
  return posthog.isFeatureEnabled(flag) === true;
};

/** `"loading"` until PostHog has answered once, so gated UI neither flashes nor redirects early. */
export const useFeatureFlag = (flag: FeatureFlag): boolean | "loading" => {
  const [value, setValue] = useState(() => read(flag));
  useEffect(() => {
    const update = () => setValue(read(flag));
    update();
    listeners.add(update);
    return () => {
      listeners.delete(update);
    };
  }, [flag]);
  return value;
};
