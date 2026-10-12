import posthog from "posthog-js";
import { eventSchemas, groupsFor } from "@gradiated/analytics";

export { posthog };
export const posthogKey = import.meta.env.VITE_POSTHOG_KEY;

if (posthogKey) {
  posthog.init(posthogKey, {
    api_host: import.meta.env.VITE_POSTHOG_HOST ?? "https://us.i.posthog.com",
    person_profiles: "identified_only",
    capture_pageview: "history_change",
    autocapture: false,
    capture_pageleave: false,
    save_referrer: false,
    save_campaign_params: false,
    before_send: (event) => {
      if (!event) return null;

      if (event.event === "$pageview") {
        event.properties.source = "console";
        event.properties.schema_version = 1;
      }

      // The SDK merges persisted groups into event groups before this hook.
      if (event.event in eventSchemas)
        event.properties.$groups = groupsFor(event.properties);

      for (const properties of [
        event.properties,
        event.properties.$set_once,
        event.properties.$set,
        event.$set_once,
        event.$set,
      ]) {
        if (!properties || typeof properties !== "object") continue;
        for (const key of [
          "$current_url",
          "$referrer",
          "$pathname",
          "$initial_current_url",
          "$initial_referrer",
          "$initial_pathname",
          "$session_entry_url",
          "$session_entry_referrer",
          "$session_entry_pathname",
        ]) {
          if (event.event !== "$pageview") {
            delete properties[key];
            continue;
          }

          if (
            key.endsWith("pathname") ||
            typeof properties[key] !== "string" ||
            properties[key] === "$direct"
          )
            continue;

          try {
            const url = new URL(properties[key]);
            url.search = "";
            url.hash = "";
            properties[key] = url.toString();
          } catch {
            delete properties[key];
          }
        }
      }
      return event;
    },
    // Rollouts target person properties such as email, so anonymous flags would answer wrongly.
    advanced_disable_feature_flags_on_first_load: true,
  });
}
