import { posthog, posthogKey } from "./posthog";
import { useSyncExternalStore } from "react";
import { clearAnalyticsScope } from "./analytics";

export type FeatureFlag = string;

export type FeatureFlagState = boolean | "loading";

const FLAG_LOAD_TIMEOUT_MS = 4_000;

const localOverrides = new Set(
  (import.meta.env.VITE_FEATURE_FLAGS ?? "")
    .split(",")
    .map((flag) => flag.trim())
    .filter(Boolean),
);

const listeners = new Set<() => void>();
let identifiedUserId: string | undefined;
let anonymous = false;
let flagsLoaded = false;
let loadTimeout: ReturnType<typeof setTimeout> | undefined;

const setFlagsLoaded = (loaded: boolean) => {
  flagsLoaded = loaded;
  for (const listener of listeners) listener();
};

if (posthogKey) {
  posthog.onFeatureFlags(() => {
    if (
      (identifiedUserId !== undefined &&
        posthog.get_distinct_id() === identifiedUserId) ||
      (anonymous && identifiedUserId === undefined)
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

// Public pages have no session; flags then evaluate for whoever this browser last identified as, or no one.
export const loadAnonymousFlags = () => {
  if (!posthogKey || identifiedUserId !== undefined || anonymous) return;

  anonymous = true;
  posthog.reloadFeatureFlags();
  clearTimeout(loadTimeout);
  loadTimeout = setTimeout(() => setFlagsLoaded(true), FLAG_LOAD_TIMEOUT_MS);
};

export const resetUser = () => {
  if (!posthogKey) return;

  posthog.reset();
  clearAnalyticsScope();
  identifiedUserId = undefined;
  anonymous = false;
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
