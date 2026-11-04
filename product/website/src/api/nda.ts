import type { components } from "./schema";
import { api, requireData } from "./client";

export type NdaDetails = components["schemas"]["NdaDetails"];
export type NdaDocument = components["schemas"]["NdaDocument"];

export const createNdaDocument = (
  organizationId: string,
  details: NdaDetails,
): Promise<NdaDocument> =>
  requireData(
    api.POST("/api/v1/organizations/{organization_id}/nda-documents", {
      params: { path: { organization_id: organizationId } },
      body: details,
    }),
  );

export const getNdaDocument = (
  organizationId: string,
  documentId: string,
): Promise<NdaDocument> =>
  requireData(
    api.GET(
      "/api/v1/organizations/{organization_id}/nda-documents/{document_id}",
      {
        params: {
          path: { organization_id: organizationId, document_id: documentId },
        },
      },
    ),
  );

export const createNdaSession = (
  organizationId: string,
  documentId: string,
): Promise<components["schemas"]["NdaSigningSession"]> =>
  requireData(
    api.POST(
      "/api/v1/organizations/{organization_id}/nda-documents/{document_id}/signing-sessions",
      {
        params: {
          path: { organization_id: organizationId, document_id: documentId },
        },
      },
    ),
  );
