import posthog from "posthog-js";
import { useSyncExternalStore } from "react";

export type FeatureFlag = "training";

export type FeatureFlagState = boolean | "loading";

const FLAG_LOAD_TIMEOUT_MS = 4_000;

const localOverrides = new Set(
  (import.meta.env.VITE_FEATURE_FLAGS ?? "")
    .split(",")
    .map((flag) => flag.trim())
    .filter(Boolean),
);

const posthogKey = import.meta.env.VITE_POSTHOG_KEY;
const listeners = new Set<() => void>();
let identifiedUserId: string | undefined;
let flagsLoaded = false;
let loadTimeout: ReturnType<typeof setTimeout> | undefined;

const setFlagsLoaded = (loaded: boolean) => {
  flagsLoaded = loaded;
  for (const listener of listeners) listener();
};

if (posthogKey) {
  posthog.init(posthogKey, {
    api_host: import.meta.env.VITE_POSTHOG_HOST ?? "https://us.i.posthog.com",
    person_profiles: "identified_only",
    capture_pageview: false,
    autocapture: false,
    // Rollouts target person properties such as email, so anonymous flags would answer wrongly.
    advanced_disable_feature_flags_on_first_load: true,
  });

  posthog.onFeatureFlags(() => {
    if (
      identifiedUserId !== undefined &&
      posthog.get_distinct_id() === identifiedUserId
    ) {
      clearTimeout(loadTimeout);
      setFlagsLoaded(true);
    }
  });
}

export const identifyUser = (user: { id: string; email: string }) => {
  if (!posthogKey || identifiedUserId === user.id) return;

  identifiedUserId = user.id;

  if (posthog.get_distinct_id() === user.id) {
    posthog.reloadFeatureFlags();
  } else {
    posthog.identify(user.id, { email: user.email });
  }

  clearTimeout(loadTimeout);
  // A blocked or failed flag request must not leave gated pages blank: after this, flags read as off.
  loadTimeout = setTimeout(() => setFlagsLoaded(true), FLAG_LOAD_TIMEOUT_MS);
};

export const resetUser = () => {
  if (!posthogKey) return;

  posthog.reset();
  identifiedUserId = undefined;
  clearTimeout(loadTimeout);
  setFlagsLoaded(false);
};

const subscribe = (listener: () => void) => {
  listeners.add(listener);

  return () => {
    listeners.delete(listener);
  };
};

export const readFeatureFlag = (flag: FeatureFlag): FeatureFlagState => {
  if (localOverrides.has(flag)) return true;
  if (!posthogKey) return false;
  if (!flagsLoaded) return "loading";

  return posthog.isFeatureEnabled(flag) === true;
};

export const useFeatureFlag = (flag: FeatureFlag): FeatureFlagState =>
  useSyncExternalStore(subscribe, () => readFeatureFlag(flag));
