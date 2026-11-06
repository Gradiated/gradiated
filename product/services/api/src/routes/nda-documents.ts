import { problemContent } from "@gradiated/contracts";
import { createRoute, type OpenAPIHono, z } from "@hono/zod-openapi";
import { consoleOnly } from "../http/audience.js";
import {
  recordCompletedNda,
  requireOnboardingAdmin,
  type OnboardingOrganizations,
} from "../http/onboarding-access.js";
import { ApiProblem, problems } from "../http/problems.js";
import {
  NdaDetailsSchema,
  NdaDocumentIdSchema,
  NdaDocumentSchema,
  type PandaDocNda,
} from "../legal/pandadoc.js";
import type { ApiEnvironment } from "../types.js";

const params = z.object({
  organization_id: z
    .uuid()
    .describe("The organization whose admin is signing the NDA."),
});
const documentParams = params.extend({
  document_id: NdaDocumentIdSchema.describe("The NDA's PandaDoc document ID."),
});
const errors = {
  401: {
    description: "A signed-in user is required.",
    content: problemContent,
  },
  403: {
    description: "The verified signer must manage this organization.",
    content: problemContent,
  },
  404: {
    description: "The NDA is not available to this user and organization.",
    content: problemContent,
  },
  409: {
    description: "The document is not ready for this operation.",
    content: problemContent,
  },
  422: { description: "Invalid NDA details.", content: problemContent },
  503: {
    description:
      "Embedded signing is not configured or the provider is unavailable.",
    content: problemContent,
  },
};

const create = createRoute({
  ...consoleOnly,
  method: "post",
  path: "/api/v1/organizations/{organization_id}/nda-documents",
  operationId: "createNdaDocument",
  tags: ["NDA documents"],
  summary: "Prepare a mutual NDA",
  description:
    "Creates a draft NDA from the approved PandaDoc template for the signed-in signer. Nothing is sent until signing opens.",
  request: {
    params,
    body: {
      required: true,
      content: { "application/json": { schema: NdaDetailsSchema } },
    },
  },
  responses: {
    201: {
      description: "The NDA is being prepared.",
      content: { "application/json": { schema: NdaDocumentSchema } },
    },
    ...errors,
  },
});
const read = createRoute({
  ...consoleOnly,
  method: "get",
  path: "/api/v1/organizations/{organization_id}/nda-documents/{document_id}",
  operationId: "getNdaDocument",
  tags: ["NDA documents"],
  summary: "Verify mutual NDA status",
  description:
    "Reads the authoritative PandaDoc status, bound to the current signer, organization and template version. Completed means all required signers finished, and records the organization's NDA for later onboarding steps.",
  request: { params: documentParams },
  responses: {
    200: {
      description: "The verified document status.",
      content: { "application/json": { schema: NdaDocumentSchema } },
    },
    ...errors,
  },
});
const session = createRoute({
  ...consoleOnly,
  method: "post",
  path: "/api/v1/organizations/{organization_id}/nda-documents/{document_id}/signing-sessions",
  operationId: "createNdaSigningSession",
  tags: ["NDA documents"],
  summary: "Open embedded NDA signing",
  description:
    "Sends a ready draft through PandaDoc, which emails the signer a copy of the document, then creates a 15-minute embedded signing session only for the verified signed-in signer.",
  request: { params: documentParams },
  responses: {
    201: {
      description: "A short-lived PandaDoc session; do not log or persist it.",
      content: {
        "application/json": {
          schema: z
            .object({ session_id: z.string() })
            .openapi("NdaSigningSession"),
        },
      },
    },
    ...errors,
  },
});

export const registerNdaDocumentRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  organizations: OnboardingOrganizations,
  provider?: PandaDocNda,
) => {
  const authorize = async (
    context: Parameters<typeof requireOnboardingAdmin>[0],
    organizationId: string,
  ) => {
    const { owner } = await requireOnboardingAdmin(
      context,
      organizations,
      organizationId,
    );
    if (!provider)
      throw new ApiProblem(
        problems.unavailable(
          "On-page NDA signing has not been configured yet.",
        ),
      );

    return { owner, provider };
  };

  app.openapi(create, async (context) => {
    context.header("Cache-Control", "no-store");
    const { owner, provider } = await authorize(
      context,
      context.req.valid("param").organization_id,
    );

    return context.json(
      await provider.create(owner, context.req.valid("json")),
      201,
    );
  });
  app.openapi(read, async (context) => {
    context.header("Cache-Control", "no-store");
    const { organization_id, document_id } = context.req.valid("param");
    const { owner, provider } = await authorize(context, organization_id);
    const document = await provider.read(owner, document_id);
    await recordCompletedNda(organizations, provider, owner, document);

    return context.json(document, 200);
  });
  app.openapi(session, async (context) => {
    context.header("Cache-Control", "no-store");
    const { organization_id, document_id } = context.req.valid("param");
    const { owner, provider } = await authorize(context, organization_id);

    return context.json(await provider.session(owner, document_id), 201);
  });
};
