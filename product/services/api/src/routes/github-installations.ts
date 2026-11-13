import { problemContent } from "@gradiated/contracts";
import { createRoute, type OpenAPIHono, z } from "@hono/zod-openapi";
import {
  GithubInstallationsSchema,
  type GithubInstallations,
} from "../github/installations.js";
import { consoleOnly } from "../http/audience.js";
import {
  requireOnboardingAdmin,
  type OnboardingOrganizations,
} from "../http/onboarding-access.js";
import { ApiProblem, problems } from "../http/problems.js";
import type { ApiEnvironment, AuthService } from "../types.js";

const read = createRoute({
  ...consoleOnly,
  method: "get",
  path: "/api/v1/organizations/{organization_id}/github-installations",
  operationId: "getGithubInstallations",
  tags: ["GitHub installations"],
  summary: "Verify the customer's Gradiated GitHub App installation",
  description:
    "Uses the signed-in customer's linked GitHub App user authorization to check active installations, Contents access and accessible repositories. Requires organization admin membership. Callback IDs and browser state are never proof of installation.",
  request: {
    params: z.object({
      organization_id: z
        .uuid()
        .describe("The authorized Gradiated organization."),
    }),
    query: z.object({
      installation_id: z.coerce
        .number()
        .int()
        .positive()
        .optional()
        .describe(
          "An installation to recheck; never trusted without GitHub verification.",
        ),
    }),
  },
  responses: {
    200: {
      description: "GitHub-confirmed current installation state.",
      content: { "application/json": { schema: GithubInstallationsSchema } },
    },
    ...Object.fromEntries(
      [401, 403, 409, 422, 503].map((status) => [
        status,
        {
          description:
            "Unauthorized, incomplete, invalid or unavailable verification.",
          content: problemContent,
        },
      ]),
    ),
  },
});

export const registerGithubInstallationRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  organizations: OnboardingOrganizations,
  auth: AuthService,
  provider?: GithubInstallations,
) => {
  app.openapi(read, async (context) => {
    context.header("Cache-Control", "no-store");
    const { organization_id } = context.req.valid("param");
    await requireOnboardingAdmin(context, organizations, organization_id);
    if (!provider || !auth.githubAccessToken)
      throw new ApiProblem(
        problems.unavailable(
          "GitHub installation verification has not been configured yet.",
        ),
      );

    const query = context.req.valid("query");

    const token = await auth
      .githubAccessToken(context.req.raw.headers)
      .catch((error: unknown) => {
        if (error instanceof ApiProblem) throw error;

        throw new ApiProblem(
          problems.unavailable(
            "Could not read your GitHub authorization. Try again shortly.",
          ),
          error,
        );
      });
    if (!token)
      return context.json(
        { status: "authorization_required" as const, installations: [] },
        200,
      );

    return context.json(await provider.list(token, query.installation_id), 200);
  });
};
