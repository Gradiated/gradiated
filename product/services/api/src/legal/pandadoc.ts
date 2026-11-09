import { z } from "@hono/zod-openapi";
import { ApiProblem, problems } from "../http/problems.js";
import { serviceLog } from "../logging.js";

export const NdaDocumentIdSchema = z
  .string()
  .regex(/^[a-zA-Z0-9_-]{1,100}$/)
  .describe(
    "A completed NDA for this organization and signed-in user. Needed only until the organization's NDA is recorded.",
  );

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
    details: NdaDetailsSchema.nullable().describe(
      "The signer details bound to the document; null while PandaDoc is still preparing it.",
    ),
    completed_at: z.iso
      .datetime({ offset: true })
      .nullable()
      .describe("When PandaDoc recorded every required signature."),
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
  date_completed: z.string().nullish(),
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
export type NdaDocument = z.infer<typeof NdaDocumentSchema>;
type Owner = { organizationId: string; userId: string; email: string };

// PandaDoc limits each metadata value to 100 characters.
const encodeDetails = (details: NdaDetails) =>
  Object.fromEntries(
    Object.entries(details).flatMap(([field, value]) => {
      const characters = Array.from(value);
      const chunks = Array.from(
        { length: Math.ceil(characters.length / 100) },
        (_, index) => characters.slice(index * 100, (index + 1) * 100).join(""),
      );

      return [
        [`gradiated_${field}_parts`, String(chunks.length)],
        ...chunks.map((chunk, index) => [`gradiated_${field}_${index}`, chunk]),
      ];
    }),
  );

const decodeDetails = (metadata: Record<string, unknown>) =>
  Object.fromEntries(
    Object.keys(NdaDetailsSchema.shape).map((field) => {
      const count = Number(metadata[`gradiated_${field}_parts`]);

      if (!Number.isInteger(count) || count < 1 || count > 10)
        throw new Error("Invalid NDA details metadata");

      const chunks = Array.from({ length: count }, (_, index) => {
        const chunk = metadata[`gradiated_${field}_${index}`];

        if (typeof chunk !== "string")
          throw new Error("Incomplete NDA details metadata");

        return chunk;
      });

      return [field, chunks.join("")];
    }),
  );

export const GRADIATED_NDA_TEMPLATE = {
  templateId: "bTmxaYhTaU2tQ28fLhVrHn",
  templateVersion: "1",
  dateField: "Agreement.Date",
  countersigner: {
    company: "PostHog Inc.",
    name: "James Hawkins",
    title: "Co-CEO",
  },
};

export interface PandaDocConfiguration {
  apiKey: string;
  templateId: string;
  templateVersion: string;
  dateField?: string | undefined;
  countersigner: { company: string; name: string; title: string };
}

const PREPARING_DEADLINE_MS = 10_000;
const PREPARING_RETRY_MS = 500;
const preparing = Symbol("preparing");

const isUploading = (result: unknown) =>
  typeof result === "object" &&
  result !== null &&
  "status" in result &&
  result.status === "document.uploaded";

export const createPandaDocNda = (
  configuration: PandaDocConfiguration,
  request: typeof fetch = fetch,
) => {
  const unavailable = (reason: string, status?: number) => {
    serviceLog("warn", "provider_request_failed", {
      dependency: "pandadoc",
      reason,
      ...(status === undefined ? {} : { status }),
    });

    return new ApiProblem(
      problems.unavailable(
        "NDA signing is temporarily unavailable. Please retry.",
      ),
    );
  };

  const send = async (path: string, body?: unknown, timeoutMs = 15_000) => {
    let response: Response;
    try {
      response = await request(`https://api.pandadoc.com/public/v1${path}`, {
        method: body === undefined ? "GET" : "POST",
        headers: {
          Authorization: `API-Key ${configuration.apiKey}`,
          "Content-Type": "application/json",
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        signal: AbortSignal.timeout(timeoutMs),
        redirect: "error",
      });
    } catch (error) {
      throw unavailable(
        error instanceof Error && error.name === "TimeoutError"
          ? "timeout"
          : "network",
      );
    }

    if (response.status === 404) {
      serviceLog("warn", "provider_request_failed", {
        dependency: "pandadoc",
        reason: "not_found",
        status: 404,
      });
      throw new ApiProblem(problems.notFound("NDA document not found."));
    }

    let result: unknown;
    try {
      const text = await response.text();
      result = text ? (JSON.parse(text) as unknown) : {};
    } catch {
      throw unavailable("invalid_response", response.status);
    }

    return { status: response.status, ok: response.ok, result };
  };

  const call = async (path: string, body: unknown) => {
    const response = await send(path, body);
    if (!response.ok) throw unavailable("http_error", response.status);

    return response.result;
  };

  const readDetails = async (id: string) => {
    const deadline = Date.now() + PREPARING_DEADLINE_MS;
    const path = `/documents/${encodeURIComponent(id)}/details`;

    for (;;) {
      const response = await send(
        path,
        undefined,
        Math.max(1, Math.min(15_000, deadline - Date.now())),
      );
      if (response.ok) return response.result;

      if (response.status !== 409 || !isUploading(response.result))
        throw unavailable("http_error", response.status);

      if (Date.now() + PREPARING_RETRY_MS >= deadline) return preparing;

      await new Promise((resolve) => setTimeout(resolve, PREPARING_RETRY_MS));
    }
  };

  const inspect = async (owner: Owner, id: string) => {
    const provided = await readDetails(id);
    if (provided === preparing) return preparing;

    const result = ProviderDocumentSchema.safeParse(provided);

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
      storedDetails = decodeDetails(metadata);
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
    const inspected = await inspect(owner, id);
    if (inspected === preparing)
      return NdaDocumentSchema.parse({
        id,
        status: "preparing",
        details: null,
        completed_at: null,
        customer_completed: false,
      });

    const { document, details } = inspected;
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

    const completedAt = Date.parse(document.date_completed ?? "");

    return NdaDocumentSchema.parse({
      id: document.id,
      status,
      details,
      completed_at:
        status === "completed"
          ? new Date(
              Number.isNaN(completedAt) ? Date.now() : completedAt,
            ).toISOString()
          : null,
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
        "PostHog.Company": configuration.countersigner.company,
        "PostHog.Signer": configuration.countersigner.name,
        "PostHog.Title": configuration.countersigner.title,
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
            ...encodeDetails(details),
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
        completed_at: null,
        customer_completed: false,
      });
    },
    read,
    templateVersion: configuration.templateVersion,
    async session(owner: Owner, id: string) {
      const inspected = await inspect(owner, id);
      if (inspected === preparing)
        throw new ApiProblem(
          problems.conflict(
            "The NDA is still being prepared. Refresh its status shortly.",
          ),
        );

      const { document } = inspected;
      if (document.status === "document.draft")
        await call(`/documents/${encodeURIComponent(id)}/send`, {
          silent: false,
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
