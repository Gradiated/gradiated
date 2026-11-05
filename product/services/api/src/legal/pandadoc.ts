import { z } from "@hono/zod-openapi";
import { ApiProblem, problems } from "../http/problems.js";

export const NdaDetailsSchema = z
  .strictObject({
    company: z
      .string()
      .trim()
      .min(1)
      .max(200)
      .describe("The counterparty's legal company name."),
    address: z
      .string()
      .trim()
      .min(1)
      .max(1000)
      .describe("The counterparty's company address."),
    name: z
      .string()
      .trim()
      .min(1)
      .max(100)
      .describe("The authorized customer signer's full name."),
    title: z
      .string()
      .trim()
      .min(1)
      .max(100)
      .describe("The customer signer's title."),
    email: z
      .string()
      .trim()
      .toLowerCase()
      .email()
      .max(200)
      .describe(
        "The signer email, which must match the authenticated verified account.",
      ),
  })
  .openapi("NdaDetails");

export const NdaDocumentSchema = z
  .object({
    id: z
      .string()
      .describe("The PandaDoc document ID, not a signing-session credential."),
    status: z
      .enum(["preparing", "ready", "completed", "unavailable"])
      .describe(
        "Authoritative provider status; completed requires all required participants.",
      ),
    details: NdaDetailsSchema,
    customer_completed: z
      .boolean()
      .describe(
        "Whether the customer recipient has finished; this alone does not complete a two-party NDA.",
      ),
  })
  .openapi("NdaDocument");

const ProviderDocumentSchema = z.object({
  id: z.string().regex(/^[a-zA-Z0-9_-]{1,100}$/),
  status: z.string(),
  metadata: z.record(z.string(), z.unknown()).optional(),
  recipients: z
    .array(
      z.object({ email: z.string(), has_completed: z.boolean().optional() }),
    )
    .optional(),
  fields: z
    .array(
      z.object({
        type: z.string(),
        is_filled: z.boolean().optional(),
        value: z.unknown().optional(),
        assigned_to: z.object({ email: z.string().optional() }).nullish(),
      }),
    )
    .optional(),
});

export type NdaDetails = z.infer<typeof NdaDetailsSchema>;
type Owner = { organizationId: string; userId: string; email: string };

export interface PandaDocConfiguration {
  apiKey: string;
  templateId: string;
  templateVersion: string;
  dateField?: string | undefined;
}

export const createPandaDocNda = (
  configuration: PandaDocConfiguration,
  request: typeof fetch = fetch,
) => {
  const call = async (path: string, body?: unknown) => {
    try {
      const response = await request(
        `https://api.pandadoc.com/public/v1${path}`,
        {
          method: body === undefined ? "GET" : "POST",
          headers: {
            Authorization: `API-Key ${configuration.apiKey}`,
            "Content-Type": "application/json",
          },
          ...(body === undefined ? {} : { body: JSON.stringify(body) }),
          signal: AbortSignal.timeout(15_000),
          redirect: "error",
        },
      );

      if (response.status === 404)
        throw new ApiProblem(problems.notFound("NDA document not found."));

      if (!response.ok) throw new Error("PandaDoc request failed");

      const text = await response.text();

      return text ? (JSON.parse(text) as unknown) : {};
    } catch (error) {
      if (error instanceof ApiProblem) throw error;

      throw new ApiProblem(
        problems.unavailable(
          "NDA signing is temporarily unavailable. Please retry.",
        ),
      );
    }
  };

  const inspect = async (owner: Owner, id: string) => {
    const result = ProviderDocumentSchema.safeParse(
      await call(`/documents/${encodeURIComponent(id)}/details`),
    );

    if (!result.success)
      throw new ApiProblem(
        problems.unavailable("Could not verify the NDA document."),
      );

    const document = result.data;
    const metadata = document.metadata;

    if (
      metadata?.gradiated_purpose !== "mutual-nda" ||
      metadata.gradiated_organization_id !== owner.organizationId ||
      metadata.gradiated_user_id !== owner.userId ||
      metadata.gradiated_template_id !== configuration.templateId ||
      metadata.gradiated_template_version !== configuration.templateVersion
    )
      throw new ApiProblem(problems.notFound("NDA document not found."));

    let storedDetails: unknown;
    try {
      storedDetails = JSON.parse(String(metadata.gradiated_details));
    } catch {
      throw new ApiProblem(problems.notFound("NDA document not found."));
    }
    const details = NdaDetailsSchema.safeParse(storedDetails);

    if (
      !details.success ||
      details.data.email !== owner.email.toLowerCase() ||
      !document.recipients?.some(
        (recipient) => recipient.email.toLowerCase() === details.data.email,
      )
    )
      throw new ApiProblem(
        problems.forbidden(
          "Sign in with the NDA signer's verified email address.",
        ),
      );

    if (
      document.status !== "document.uploaded" &&
      !document.fields?.some(
        (field) =>
          field.type === "signature" &&
          field.assigned_to?.email?.toLowerCase() === details.data.email,
      )
    )
      throw new ApiProblem(
        problems.unavailable(
          "The NDA template needs a signature field assigned to the customer.",
        ),
      );

    if (
      document.status === "document.completed" &&
      !document.fields?.some((field) => {
        if (
          field.type !== "signature" ||
          field.assigned_to?.email?.toLowerCase() !== details.data.email
        )
          return false;
        if (field.is_filled === true) return true;
        if (typeof field.value === "string")
          return field.value.trim().length > 0;

        return (
          typeof field.value === "object" &&
          field.value !== null &&
          Object.keys(field.value).length > 0
        );
      })
    )
      throw new ApiProblem(
        problems.unavailable(
          "Could not verify the customer's signature on this NDA.",
        ),
      );

    return { document, details: details.data };
  };

  const read = async (owner: Owner, id: string) => {
    const { document, details } = await inspect(owner, id);
    const customerCompleted =
      document.recipients?.some(
        (recipient) =>
          recipient.email.toLowerCase() === owner.email.toLowerCase() &&
          recipient.has_completed === true,
      ) ?? false;
    const status =
      document.status === "document.completed" && customerCompleted
        ? "completed"
        : document.status === "document.uploaded"
          ? "preparing"
          : ["document.draft", "document.sent", "document.viewed"].includes(
                document.status,
              )
            ? "ready"
            : "unavailable";

    return NdaDocumentSchema.parse({
      id: document.id,
      status,
      details,
      customer_completed: customerCompleted,
    });
  };

  return {
    async create(owner: Owner, value: NdaDetails) {
      const details = NdaDetailsSchema.parse(value);

      if (details.email !== owner.email.toLowerCase())
        throw new ApiProblem(
          problems.forbidden(
            "Sign in with the NDA signer's verified email address.",
          ),
        );

      const [firstName, ...rest] = details.name.split(/\s+/);
      const values = {
        "Customer.Company": details.company,
        "Customer.Address": details.address,
        "Customer.Name": details.name,
        "Customer.Title": details.title,
        "Customer.Email": details.email,
        "PostHog.Company": "PostHog Inc.",
        "PostHog.Signer": "James Hawkins",
        "PostHog.Title": "Co-CEO",
      };
      const result = ProviderDocumentSchema.safeParse(
        await call("/documents", {
          name: `Mutual NDA — ${details.company}`,
          template_uuid: configuration.templateId,
          recipients: [
            {
              email: details.email,
              first_name: firstName,
              last_name: rest.join(" "),
              role: "Customer",
            },
          ],
          tokens: Object.entries(values).map(([name, value]) => ({
            name,
            value,
          })),
          fields: {
            ...Object.fromEntries(
              Object.entries(values).map(([name, value]) => [name, { value }]),
            ),
            ...(configuration.dateField
              ? {
                  [configuration.dateField]: {
                    value: new Date().toISOString(),
                  },
                }
              : {}),
          },
          metadata: {
            gradiated_purpose: "mutual-nda",
            gradiated_organization_id: owner.organizationId,
            gradiated_user_id: owner.userId,
            gradiated_template_id: configuration.templateId,
            gradiated_template_version: configuration.templateVersion,
            gradiated_details: JSON.stringify(details),
          },
        }),
      );

      if (!result.success)
        throw new ApiProblem(
          problems.unavailable(
            "Could not create the NDA. Check PandaDoc before creating another copy.",
          ),
        );

      return NdaDocumentSchema.parse({
        id: result.data.id,
        status: "preparing",
        details,
        customer_completed: false,
      });
    },
    read,
    async session(owner: Owner, id: string) {
      const { document } = await inspect(owner, id);

      if (document.status === "document.draft")
        await call(`/documents/${encodeURIComponent(id)}/send`, {
          silent: true,
        });
      else if (!["document.sent", "document.viewed"].includes(document.status))
        throw new ApiProblem(
          problems.conflict(
            "The NDA is not ready for signing. Refresh its status.",
          ),
        );

      const session = z.object({ id: z.string().min(1).max(200) }).safeParse(
        await call(`/documents/${encodeURIComponent(id)}/session`, {
          recipient: owner.email,
          lifetime: 900,
        }),
      );

      if (!session.success)
        throw new ApiProblem(
          problems.unavailable("Could not open the signing session."),
        );

      return { session_id: session.data.id };
    },
  };
};

export type PandaDocNda = ReturnType<typeof createPandaDocNda>;
