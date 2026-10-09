import {
  createAnalytics,
  groupSchemas,
  type AnalyticsEvent,
  type AnalyticsGroup,
  type EventProperties,
  type GroupProperties,
} from "./index.js";

export const createPostHogServer = ({
  key,
  host = "https://us.i.posthog.com",
  fetch: send = globalThis.fetch,
  onError = () => undefined,
}: {
  key?: string | undefined;
  host?: string | undefined;
  fetch?: typeof globalThis.fetch;
  onError?: () => void;
}) => {
  const pending = new Set<Promise<void>>();
  const endpoint = new URL("/capture/", host).toString();
  const reportError = () => {
    try {
      onError();
    } catch {
      return;
    }
  };

  const enqueue = (
    distinctId: string,
    event: string,
    properties: Record<string, unknown>,
    uuid: string,
  ) => {
    if (!key) return;
    if (pending.size >= 1000) {
      reportError();
      return;
    }

    const timestamp = new Date().toISOString();
    const delivery = (async () => {
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const response = await send(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              api_key: key,
              event,
              distinct_id: distinctId,
              properties,
              uuid,
              timestamp,
            }),
            signal: AbortSignal.timeout(3000),
          });
          await response.body?.cancel();
          if (response.ok) return;
          if (response.status < 500 && response.status !== 429) break;
        } catch {
          if (attempt === 1) break;
        }
      }
      reportError();
    })();
    pending.add(delivery);
    void delivery.finally(() => pending.delete(delivery));
  };

  return {
    enabled: Boolean(key),
    track: <Event extends AnalyticsEvent>(
      userId: string,
      event: Event,
      properties: EventProperties<Event>,
      eventId?: string,
      person?: { email: string },
    ) =>
      createAnalytics("api", (name, payload) =>
        enqueue(
          userId,
          name,
          { ...payload, ...(person ? { $set: { email: person.email } } : {}) },
          eventId ?? crypto.randomUUID(),
        ),
      ).track(event, properties),
    group: <Group extends AnalyticsGroup>(
      userId: string,
      type: Group,
      groupId: string,
      properties: GroupProperties<Group>,
    ) => {
      const parsed = groupSchemas[type].safeParse(properties);
      if (!parsed.success) return;

      enqueue(
        userId,
        "$groupidentify",
        {
          $group_type: type,
          $group_key: groupId,
          $group_set: parsed.data,
        },
        crypto.randomUUID(),
      );
    },
    flush: async () => {
      await Promise.all(pending);
    },
  };
};

export type PostHogServer = ReturnType<typeof createPostHogServer>;
