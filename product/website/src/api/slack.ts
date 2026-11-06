import type { components } from "./schema";
import { api, requireData } from "./client";

export type SlackInvitation = components["schemas"]["SlackInvitation"];

export const createSlackInvitation = (
  organizationId: string,
  invitation: { email: string; channelName?: string; ndaDocumentId?: string },
): Promise<SlackInvitation> =>
  requireData(
    api.POST("/api/v1/organizations/{organization_id}/slack-invitations", {
      params: { path: { organization_id: organizationId } },
      body: {
        email: invitation.email,
        ...(invitation.channelName
          ? { channel_name: invitation.channelName }
          : {}),
        ...(invitation.ndaDocumentId
          ? { nda_document_id: invitation.ndaDocumentId }
          : {}),
      },
    }),
  );
