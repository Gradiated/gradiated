import { api, requireData } from "./client";

export const createSlackInvitation = (
  organizationId: string,
  ndaDocumentId: string,
) =>
  requireData(
    api.POST("/api/v1/organizations/{organization_id}/slack-invitations", {
      params: { path: { organization_id: organizationId } },
      body: { nda_document_id: ndaDocumentId },
    }),
  );
