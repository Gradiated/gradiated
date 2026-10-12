import posthog from "posthog-js";

const key = import.meta.env.VITE_POSTHOG_KEY;

if (key) {
  posthog.init(key, {
    api_host: import.meta.env.VITE_POSTHOG_HOST || "https://us.i.posthog.com",
    person_profiles: "identified_only",
    capture_pageview: "history_change",
    capture_pageleave: false,
    autocapture: false,
    capture_exceptions: false,
    capture_performance: false,
    capture_dead_clicks: false,
    enable_heatmaps: false,
    disable_surveys: true,
    advanced_disable_feature_flags_on_first_load: true,
    save_referrer: false,
    save_campaign_params: false,
    before_send: (event) => {
      if (!event || !["$pageview", "$snapshot"].includes(event.event))
        return null;

      event.properties.source = "website";
      event.properties.schema_version = 1;

      for (const properties of [
        event.properties,
        event.properties.$set_once,
        event.properties.$set,
        event.$set_once,
        event.$set,
      ]) {
        if (!properties || typeof properties !== "object") continue;

        for (const name of [
          "$current_url",
          "$referrer",
          "$initial_current_url",
          "$initial_referrer",
          "$session_entry_url",
          "$session_entry_referrer",
        ]) {
          if (
            typeof properties[name] !== "string" ||
            properties[name] === "$direct"
          )
            continue;

          try {
            const url = new URL(properties[name]);
            url.search = "";
            url.hash = "";
            properties[name] = url.toString();
          } catch {
            delete properties[name];
          }
        }
      }

      return event;
    },
  });
}
