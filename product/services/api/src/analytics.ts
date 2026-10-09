import {
  eventSchemas,
  type AnalyticsEvent,
  type EventProperties,
  type WorkspaceEvent,
} from "@gradiated/analytics";
import type { PostHogServer } from "@gradiated/analytics/server";

export const createApiAnalytics = (
  client: PostHogServer,
  resolveOrganization: (workspaceId: string) => Promise<string | undefined>,
  onError: () => void,
) => {
  const pending = new Set<Promise<void>>();
  const reportError = () => {
    try {
      onError();
    } catch {
      return;
    }
  };

  return {
    track: <Event extends AnalyticsEvent>(
      userId: string,
      event: Event,
      properties: EventProperties<Event>,
    ) => {
      if (event === "workspace_created") {
        const parsed = eventSchemas.workspace_created.safeParse(properties);
        if (parsed.success)
          client.group(userId, "workspace", parsed.data.workspace_id, {
            organization_id: parsed.data.organization_id,
            is_default: parsed.data.is_default,
          });
      }
      if (event === "organization_created") {
        const parsed = eventSchemas.organization_created.safeParse(properties);
        if (parsed.success)
          client.group(userId, "organization", parsed.data.organization_id, {
            status: "active",
          });
      }

      if (!client.track(userId, event, properties)) reportError();
    },
    trackWorkspace: <Event extends WorkspaceEvent>(
      userId: string,
      event: Event,
      properties: Omit<EventProperties<Event>, "organization_id"> & {
        workspace_id: string;
      },
    ) => {
      if (!client.enabled) return;
      if (pending.size >= 1000) return reportError();

      const delivery = (async () => {
        try {
          const organizationId = await resolveOrganization(
            properties.workspace_id,
          );
          if (!organizationId) return reportError();

          client.track(userId, event, {
            ...properties,
            organization_id: organizationId,
          } as EventProperties<Event>);
        } catch {
          reportError();
        }
      })();
      pending.add(delivery);
      void delivery.finally(() => pending.delete(delivery));
    },
    flush: async () => {
      await Promise.all(pending);
      await client.flush();
    },
  };
};

export type ApiAnalytics = ReturnType<typeof createApiAnalytics>;

export const createSignupHandler =
  (
    ensureOrganization: (
      userId: string,
    ) => Promise<{ id: string; defaultWorkspaceId: string }>,
    client: PostHogServer,
  ) =>
  async (user: { id: string; email: string }) => {
    const organization = await ensureOrganization(user.id);
    client.group(user.id, "organization", organization.id, {
      status: "active",
    });
    client.group(user.id, "workspace", organization.defaultWorkspaceId, {
      organization_id: organization.id,
      is_default: true,
    });
    client.track(
      user.id,
      "user_signed_up",
      {
        user_id: user.id,
        organization_id: organization.id,
        workspace_id: organization.defaultWorkspaceId,
      },
      user.id,
      { email: user.email },
    );
  };
