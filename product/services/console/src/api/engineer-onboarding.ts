import { api, requireData } from "./client";
import type { components } from "./schema";

export type EngineerOnboarding = components["schemas"]["EngineerOnboarding"];
export type EngineerOnboardingSubmission =
  components["schemas"]["EngineerOnboardingSubmission"];
export type GithubInstallation = components["schemas"]["GithubInstallation"];
export type NdaDetails = NonNullable<components["schemas"]["NdaDetails"]>;
export type NdaDocument = components["schemas"]["NdaDocument"];

const organization = (organization_id: string) => ({ organization_id });

export const getEngineerOnboarding = (organizationId: string) =>
  requireData(
    api.GET("/api/v1/organizations/{organization_id}/engineer-onboarding", {
      params: { path: organization(organizationId) },
    }),
  );

export const submitEngineerOnboarding = (
  organizationId: string,
  body: EngineerOnboardingSubmission,
) =>
  requireData(
    api.POST(
      "/api/v1/organizations/{organization_id}/engineer-onboarding/submission",
      { params: { path: organization(organizationId) }, body },
    ),
  );

export const getGithubInstallations = (
  organizationId: string,
  {
    ndaDocumentId,
    installationId,
  }: {
    ndaDocumentId?: string | undefined;
    installationId?: number | undefined;
  } = {},
) =>
  requireData(
    api.GET("/api/v1/organizations/{organization_id}/github-installations", {
      params: {
        path: organization(organizationId),
        query: {
          ...(ndaDocumentId ? { nda_document_id: ndaDocumentId } : {}),
          ...(installationId ? { installation_id: installationId } : {}),
        },
      },
    }),
  );

export const createSlackInvitation = (
  organizationId: string,
  invitation: {
    email: string;
    channelName?: string | undefined;
    ndaDocumentId?: string | undefined;
  },
) =>
  requireData(
    api.POST("/api/v1/organizations/{organization_id}/slack-invitations", {
      params: { path: organization(organizationId) },
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

export const createNdaDocument = (organizationId: string, body: NdaDetails) =>
  requireData(
    api.POST("/api/v1/organizations/{organization_id}/nda-documents", {
      params: { path: organization(organizationId) },
      body,
    }),
  );

export const getNdaDocument = (organizationId: string, documentId: string) =>
  requireData(
    api.GET(
      "/api/v1/organizations/{organization_id}/nda-documents/{document_id}",
      {
        params: {
          path: { ...organization(organizationId), document_id: documentId },
        },
      },
    ),
  );

export const createNdaSession = (organizationId: string, documentId: string) =>
  requireData(
    api.POST(
      "/api/v1/organizations/{organization_id}/nda-documents/{document_id}/signing-sessions",
      {
        params: {
          path: { ...organization(organizationId), document_id: documentId },
        },
      },
    ),
  );
