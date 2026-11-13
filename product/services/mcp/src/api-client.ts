import {
  CredentialIdentitySchema,
  PlaygroundCredentialSchema,
  type CredentialIdentity,
} from "@gradiated/contracts";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";

import type { ToolOutcome } from "./metrics.js";
import type { ToolDefinition } from "./tools/definitions.js";

// Keeps one tool result within a model's context.
export const MAX_RESULT_CHARACTERS = 100_000;

const API_TIMEOUT_MS = 30_000;
const INFERENCE_TIMEOUT_MS = 300_000;

export interface Caller {
  credential: string;
  // The end client's address, so the API's per-IP limits apply to it and not to this service.
  forwardedFor: string | undefined;
}

export interface Principal {
  caller: Caller;
  identity: CredentialIdentity;
}

export interface InferenceKey {
  secret: string;
  expiresAt: number;
}

export interface ToolCall {
  result: CallToolResult;
  outcome: ToolOutcome;
}

// Supplies the key a model call is sent with; renew asks for a fresh one after a rejection.
export type InferenceAuthorization = (renew: boolean) => Promise<string>;

export type ApiClient = ReturnType<typeof createApiClient>;

const failure = (text: string, outcome: ToolOutcome): ToolCall => ({
  outcome,
  result: { isError: true, content: [{ type: "text", text }] },
});

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const appendQuery = (url: URL, field: string, value: unknown) => {
  for (const item of Array.isArray(value) ? value : [value])
    url.searchParams.append(
      field,
      isRecord(item) ? JSON.stringify(item) : String(item),
    );
};

const outcomeOf = (status: number): ToolOutcome =>
  status < 400 ? "success" : status < 500 ? "rejected" : "failed";

const toolResult = (
  tool: ToolDefinition,
  response: Response,
  text: string,
): ToolCall => {
  const outcome = outcomeOf(response.status);
  if (text.length > MAX_RESULT_CHARACTERS)
    return failure(
      `The result has ${text.length} characters, over the ${MAX_RESULT_CHARACTERS} limit. Narrow the request, for example with a shorter period, a filter or a smaller page.`,
      response.ok ? "rejected" : outcome,
    );
  if (!response.ok) return failure(text || response.statusText, outcome);

  let structured: unknown;
  try {
    structured = text ? JSON.parse(text) : undefined;
  } catch {
    structured = undefined;
  }

  return {
    outcome,
    result: {
      content: [{ type: "text", text: text || "{}" }],
      ...(tool.outputSchema && isRecord(structured)
        ? { structuredContent: structured }
        : {}),
    },
  };
};

export const createApiClient = (
  apiUrl: string,
  inferenceUrl: string,
  fetchApi: typeof fetch = fetch,
) => {
  const request = (
    caller: Caller,
    url: URL,
    init: RequestInit & { authorization?: string; timeoutMs?: number } = {},
  ) => {
    const { authorization, timeoutMs, ...rest } = init;

    return fetchApi(url, {
      ...rest,
      redirect: "error",
      signal: AbortSignal.timeout(timeoutMs ?? API_TIMEOUT_MS),
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${authorization ?? caller.credential}`,
        ...(caller.forwardedFor
          ? { "X-Forwarded-For": caller.forwardedFor }
          : {}),
        ...rest.headers,
      },
    });
  };

  const authenticate = async (
    caller: Caller,
  ): Promise<CredentialIdentity | null> => {
    const response = await request(
      caller,
      new URL("/api/v1/credentials/current", apiUrl),
    );
    if (response.status === 401) return null;
    if (!response.ok)
      throw new Error(
        `The API answered ${response.status} for the credential.`,
      );

    return CredentialIdentitySchema.parse(await response.json());
  };

  const createInferenceKey = async (caller: Caller): Promise<InferenceKey> => {
    const response = await request(
      caller,
      new URL("/api/v1/credentials/current/inference-keys", apiUrl),
      { method: "POST" },
    );
    if (!response.ok)
      throw new Error(
        `The API answered ${response.status} for an inference key.`,
      );

    const key = PlaygroundCredentialSchema.parse(await response.json());

    return { secret: key.secret, expiresAt: Date.parse(key.expires_at) };
  };

  const call = async (
    principal: Principal,
    tool: ToolDefinition,
    input: Record<string, unknown>,
    inferenceAuthorization: InferenceAuthorization,
  ): Promise<ToolCall> => {
    const unknown = Object.keys(input).filter(
      (name) => !tool.arguments.some((argument) => argument.name === name),
    );
    if (unknown.length)
      return failure(`Unknown arguments: ${unknown.join(", ")}.`, "rejected");

    const missing = tool.inputSchema.required.filter(
      (name) => input[name] === undefined,
    );
    if (missing.length)
      return failure(`Missing arguments: ${missing.join(", ")}.`, "rejected");

    const values = [
      ...tool.fixed,
      ...tool.arguments.flatMap(({ name, field, location }) =>
        input[name] === undefined
          ? []
          : [{ field, location, value: input[name] }],
      ),
    ];
    const path = tool.path.replace(/\{(\w+)\}/g, (_, field: string) =>
      encodeURIComponent(
        String(
          field === "workspace_id"
            ? principal.identity.workspace_id
            : (values.find((value) => value.field === field)?.value ?? ""),
        ),
      ),
    );
    const url = new URL(
      path,
      tool.upstream === "inference" ? inferenceUrl : apiUrl,
    );
    const body: Record<string, unknown> = {};

    for (const { field, location, value } of values) {
      if (location === "query") appendQuery(url, field, value);
      if (location === "body") body[field] = value;
    }

    const send = async (authorization?: string) =>
      request(principal.caller, url, {
        method: tool.method.toUpperCase(),
        ...(authorization ? { authorization } : {}),
        ...(tool.upstream === "inference"
          ? { timeoutMs: INFERENCE_TIMEOUT_MS }
          : {}),
        ...(values.some(({ location }) => location === "body")
          ? {
              body: JSON.stringify(body),
              headers: { "Content-Type": "application/json" },
            }
          : {}),
      });

    try {
      let response =
        tool.upstream === "inference"
          ? await send(await inferenceAuthorization(false))
          : await send();
      // A cached inference key may have been rotated by another connection of the same member.
      if (tool.upstream === "inference" && response.status === 401)
        response = await send(await inferenceAuthorization(true));

      return toolResult(tool, response, await response.text());
    } catch (error) {
      return failure(
        error instanceof Error && error.name === "TimeoutError"
          ? "The request timed out."
          : "The request could not be completed.",
        "failed",
      );
    }
  };

  return { authenticate, createInferenceKey, call };
};
