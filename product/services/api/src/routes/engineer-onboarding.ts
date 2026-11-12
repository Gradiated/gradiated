import {
  ContactChannelSchema,
  problemContent,
  TimestampSchema,
} from "@gradiated/contracts";
import type {
  IntegrationService,
  SlackIntegrationRecord,
} from "@gradiated/control";
import { createRoute, type OpenAPIHono, z } from "@hono/zod-openapi";

import type { EngineerOnboardingNotifier } from "../email/engineer-onboarding.js";
import type { GithubInstallations } from "../github/installations.js";
import { consoleOnly } from "../http/audience.js";
import {
  requireOnboardingAdmin,
  requireRecordedNda,
  type OnboardingOrganizations,
  type OnboardingOwner,
} from "../http/onboarding-access.js";
import { ApiProblem, problems } from "../http/problems.js";
import { NdaDocumentIdSchema, type PandaDocNda } from "../legal/pandadoc.js";
import { serviceLog } from "../logging.js";
import type { SlackConnect } from "../slack/connect.js";
import type { ApiEnvironment, AuthService } from "../types.js";

export const EngineerOnboardingSchema = z
  .object({
    nda: z
      .object({
        document_id: z.string().describe("The completed PandaDoc document."),
        signed_at: TimestampSchema,
      })
      .nullable()
      .describe(
        "The organization's completed NDA, once PandaDoc confirms it. The NDA is optional.",
      ),
    slack: z
      .object({
        channel_id: z.string(),
        channel_name: z.string(),
        status: z
          .enum(["pending", "active"])
          .describe("Active once Slack confirmed an invitation."),
        invited_email: z.email().nullable(),
        invited_at: TimestampSchema.nullable(),
      })
      .nullable()
      .describe("The organization's Slack Connect channel."),
    github_installations: z
      .array(
        z.object({
          id: z.number().int().positive(),
          account: z.string(),
          repository_selection: z.enum(["all", "selected"]),
        }),
      )
      .describe("GitHub App installations recorded at submission."),
    contact_channel: ContactChannelSchema.nullable(),
    submitted_at: TimestampSchema.nullable().describe(
      "When the organization started its project; null until submitted.",
    ),
  })
  .openapi("EngineerOnboarding");

const SubmissionSchema = z
  .strictObject({
    contact_channel: ContactChannelSchema,
    github_installation_id: z
      .number()
      .int()
      .positive()
      .describe("The installation to verify with GitHub before submitting."),
    notes: z
      .string()
      .trim()
      .max(3000)
      .optional()
      .describe(
        "Optional context for Gradiated engineers. Delivered with the submission and not stored.",
      ),
    nda_document_id: NdaDocumentIdSchema.optional().describe(
      "The customer's optional NDA; when present it must be completed before submitting.",
    ),
  })
  .openapi("EngineerOnboardingSubmission");

const params = z.object({
  organization_id: z.uuid().describe("The customer organization."),
});
const errors = {
  401: {
    description: "A signed-in user is required.",
    content: problemContent,
  },
  403: {
    description: "A verified organization admin is required.",
    content: problemContent,
  },
  503: {
    description: "A provider is not configured or unavailable.",
    content: problemContent,
  },
};

const read = createRoute({
  ...consoleOnly,
  method: "get",
  path: "/api/v1/organizations/{organization_id}/engineer-onboarding",
  operationId: "getEngineerOnboarding",
  tags: ["Engineer onboarding"],
  summary: "Read the organization's engineer onboarding progress",
  request: { params },
  responses: {
    200: {
      description: "The recorded onboarding state.",
      content: { "application/json": { schema: EngineerOnboardingSchema } },
    },
    ...errors,
  },
});

const submit = createRoute({
  ...consoleOnly,
  method: "post",
  path: "/api/v1/organizations/{organization_id}/engineer-onboarding/submission",
  operationId: "submitEngineerOnboarding",
  tags: ["Engineer onboarding"],
  summary: "Start the organization's engineering project",
  description:
    "Rechecks the GitHub installation and, when nda_document_id is present, requires that NDA to be completed. Records the submission once per organization, posts nonempty notes to the organization's Slack channel when contact_channel is slack, and notifies Gradiated. A repeated submission returns the existing state with 200 and sends nothing.",
  request: {
    params,
    body: {
      required: true,
      content: { "application/json": { schema: SubmissionSchema } },
    },
  },
  responses: {
    200: {
      description: "The organization had already submitted.",
      content: { "application/json": { schema: EngineerOnboardingSchema } },
    },
    201: {
      description: "The submission was recorded.",
      content: { "application/json": { schema: EngineerOnboardingSchema } },
    },
    409: {
      description:
        "nda_required, github_authorization_required, github_installation_unverified or slack_channel_required; conflict when the installation belongs to another organization.",
      content: problemContent,
    },
    422: { description: "Invalid submission.", content: problemContent },
    ...errors,
  },
});

export const registerEngineerOnboardingRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  dependencies: {
    organizations: OnboardingOrganizations;
    integrations: IntegrationService;
    auth: AuthService;
    notify: EngineerOnboardingNotifier;
    nda?: PandaDocNda | undefined;
    slack?: SlackConnect | undefined;
    github?: GithubInstallations | undefined;
  },
) => {
  const { organizations, integrations } = dependencies;

  const state = async (owner: OnboardingOwner) => {
    const [onboarding, connected] = await Promise.all([
      organizations.getOnboarding(owner.userId, owner.organizationId),
      integrations.list(owner.userId, owner.organizationId),
    ]);
    const slack = connected.find(
      (integration): integration is SlackIntegrationRecord =>
        integration.provider === "slack",
    );

    return EngineerOnboardingSchema.parse({
      nda: onboarding.nda
        ? {
            document_id: onboarding.nda.document_id,
            signed_at: onboarding.nda.signed_at,
          }
        : null,
      slack: slack
        ? {
            channel_id: slack.externalId,
            channel_name: slack.settings.channel_name,
            status: slack.status,
            invited_email: slack.settings.invited_email ?? null,
            invited_at: slack.settings.invited_at ?? null,
          }
        : null,
      github_installations: connected.flatMap((integration) =>
        integration.provider === "github"
          ? [
              {
                id: Number(integration.externalId),
                account: integration.settings.account_login,
                repository_selection: integration.settings.repository_selection,
              },
            ]
          : [],
      ),
      contact_channel: onboarding.contact_channel ?? null,
      submitted_at: onboarding.submitted_at ?? null,
    });
  };

  const verifyInstallation = async (headers: Headers, id: number) => {
    const { auth, github } = dependencies;
    if (!github || !auth.githubAccessToken)
      throw new ApiProblem(
        problems.unavailable(
          "GitHub installation verification has not been configured yet.",
        ),
      );

    const token = await auth
      .githubAccessToken(headers)
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
      throw new ApiProblem(
        problems.onboardingConflict(
          "github_authorization_required",
          "Connect your GitHub account before starting the project.",
        ),
      );

    const verified = await github.list(token, id);
    const installation = verified.installations.find(
      (candidate) => candidate.id === id,
    );
    if (!installation)
      throw new ApiProblem(
        problems.onboardingConflict(
          "github_installation_unverified",
          "GitHub did not confirm the selected installation. Check its repository access and try again.",
        ),
      );

    return installation;
  };

  const deliver = async (
    owner: OnboardingOwner,
    organizationName: string,
    input: z.infer<typeof SubmissionSchema>,
  ) => {
    const current = await state(owner);
    const notes = input.notes || null;
    const failed = (dependency: string) => (error: unknown) =>
      serviceLog("warn", "engineer_onboarding_delivery_failed", {
        organization_id: owner.organizationId,
        dependency,
        error,
      });

    if (input.contact_channel === "slack" && notes && current.slack)
      await dependencies.slack
        ?.postNotes({
          channelId: current.slack.channel_id,
          email: owner.email,
          notes,
          requestId: owner.organizationId,
        })
        .catch(failed("slack"));

    await dependencies
      .notify({
        organizationId: owner.organizationId,
        organizationName,
        submittedByEmail: owner.email,
        contactChannel: input.contact_channel,
        githubAccounts: current.github_installations.map(
          (installation) => installation.account,
        ),
        slackChannel: current.slack?.channel_name ?? null,
        ndaSignedAt: current.nda?.signed_at ?? null,
        notes,
      })
      .catch(failed("email"));

    return current;
  };

  app.openapi(read, async (context) => {
    context.header("Cache-Control", "no-store");
    const { owner } = await requireOnboardingAdmin(
      context,
      organizations,
      context.req.valid("param").organization_id,
    );

    return context.json(await state(owner), 200);
  });

  app.openapi(submit, async (context) => {
    context.header("Cache-Control", "no-store");
    const { owner, organization } = await requireOnboardingAdmin(
      context,
      organizations,
      context.req.valid("param").organization_id,
    );
    const input = context.req.valid("json");
    const existing = await organizations.getOnboarding(
      owner.userId,
      owner.organizationId,
    );
    if (existing.submitted_at) return context.json(await state(owner), 200);

    if (input.nda_document_id) {
      if (!dependencies.nda)
        throw new ApiProblem(
          problems.unavailable(
            "NDA signing isn’t available right now. Email us the details instead and we’ll send over the NDA.",
          ),
        );

      await requireRecordedNda(
        organizations,
        dependencies.nda,
        owner,
        "starting the project",
        input.nda_document_id,
      );
    }

    const installation = await verifyInstallation(
      context.req.raw.headers,
      input.github_installation_id,
    );

    if (input.contact_channel === "slack") {
      if (!dependencies.slack)
        throw new ApiProblem(
          problems.unavailable("Slack has not been configured yet."),
        );

      if (
        !(await integrations.findSlackChannel(
          owner.userId,
          owner.organizationId,
        ))
      )
        throw new ApiProblem(
          problems.onboardingConflict(
            "slack_channel_required",
            "Request the Slack invitation before choosing Slack for contact.",
          ),
        );
    }

    await integrations.recordGithubInstallation(
      owner.userId,
      owner.organizationId,
      {
        id: installation.id,
        account_login: installation.account,
        repository_selection: installation.repository_selection,
      },
    );

    const { submitted } = await organizations.submitOnboarding(
      owner.userId,
      owner.organizationId,
      input.contact_channel,
    );
    if (!submitted) return context.json(await state(owner), 200);

    return context.json(await deliver(owner, organization.name, input), 201);
  });
};
