import { api, requireData } from "./client";

export const sendSlackOnboardingNotes = (
  organizationId: string,
  ndaDocumentId: string,
  channelName: string,
  notes: string,
  requestId: string,
) =>
  requireData(
    api.POST("/api/v1/organizations/{organization_id}/slack-messages", {
      params: { path: { organization_id: organizationId } },
      body: {
        nda_document_id: ndaDocumentId,
        channel_name: channelName,
        notes,
        request_id: requestId,
      },
    }),
  );

export const createSlackInvitation = (
  organizationId: string,
  ndaDocumentId: string,
  email: string,
  channelName?: string,
) =>
  requireData(
    api.POST("/api/v1/organizations/{organization_id}/slack-invitations", {
      params: { path: { organization_id: organizationId } },
      body: {
        nda_document_id: ndaDocumentId,
        email,
        ...(channelName ? { channel_name: channelName } : {}),
      },
    }),
  );
