import { api, requireData } from "./client";

export const getGithubInstallations = (
  organizationId: string,
  {
    ndaDocumentId,
    installationId,
  }: { ndaDocumentId?: string; installationId?: number } = {},
) =>
  requireData(
    api.GET("/api/v1/organizations/{organization_id}/github-installations", {
      params: {
        path: { organization_id: organizationId },
        query: {
          ...(ndaDocumentId ? { nda_document_id: ndaDocumentId } : {}),
          ...(installationId ? { installation_id: installationId } : {}),
        },
      },
    }),
  );
