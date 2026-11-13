import {
  ApiKeyIdentitySchema,
  type ApiKeyIdentity,
} from "@gradiated/contracts";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";

import type { ToolDefinition } from "./tools/definitions.js";

// Keeps one tool result within a model's context.
const MAX_RESULT_CHARACTERS = 100_000;

export interface Caller {
  authorization: string;
  // The end client's address, so the API's per-IP limits apply to it and not to this service.
  forwardedFor: string | undefined;
}

export interface Principal {
  caller: Caller;
  identity: ApiKeyIdentity;
}

export type ApiClient = ReturnType<typeof createApiClient>;

export const createApiClient = (
  apiUrl: string,
  fetchApi: typeof fetch = fetch,
) => {
  const request = (caller: Caller, path: string, init: RequestInit = {}) =>
    fetchApi(new URL(path, apiUrl), {
      ...init,
      redirect: "error",
      signal: AbortSignal.timeout(30_000),
      headers: {
        Accept: "application/json",
        Authorization: caller.authorization,
        ...(caller.forwardedFor
          ? { "X-Forwarded-For": caller.forwardedFor }
          : {}),
        ...init.headers,
      },
    });

  const authenticate = async (caller: Caller): Promise<Principal | null> => {
    const response = await request(caller, "/api/v1/api-keys/current");
    if (response.status === 401) return null;
    if (!response.ok)
      throw new Error(`The API answered ${response.status} for the key.`);

    return {
      caller,
      identity: ApiKeyIdentitySchema.parse(await response.json()),
    };
  };

  const call = async (
    principal: Principal,
    tool: ToolDefinition,
    input: Record<string, unknown>,
  ): Promise<CallToolResult> => {
    const unknown = Object.keys(input).filter(
      (name) => !tool.arguments.some((argument) => argument.name === name),
    );
    if (unknown.length)
      return failure(`Unknown arguments: ${unknown.join(", ")}.`);

    const missing = tool.inputSchema.required.filter(
      (name) => input[name] === undefined,
    );
    if (missing.length)
      return failure(`Missing arguments: ${missing.join(", ")}.`);

    const path = tool.path.replace(/\{(\w+)\}/g, (_, field: string) => {
      const value =
        field === "workspace_id"
          ? principal.identity.workspace_id
          : input[argumentName(tool, field)];

      return encodeURIComponent(String(value ?? ""));
    });
    const url = new URL(path, apiUrl);
    const body: Record<string, unknown> = {};

    for (const argument of tool.arguments) {
      const value = input[argument.name];
      if (value === undefined) continue;

      if (argument.location === "query")
        url.searchParams.set(argument.field, String(value));
      if (argument.location === "body") body[argument.field] = value;
    }

    const hasBody = tool.arguments.some(({ location }) => location === "body");
    const response = await request(
      principal.caller,
      url.pathname + url.search,
      {
        method: tool.method.toUpperCase(),
        ...(hasBody
          ? {
              body: JSON.stringify(body),
              headers: { "Content-Type": "application/json" },
            }
          : {}),
      },
    );

    return result(response.ok, await response.text());
  };

  return { authenticate, call };
};

const argumentName = (tool: ToolDefinition, field: string) =>
  tool.arguments.find((argument) => argument.field === field)?.name ?? field;

const failure = (text: string): CallToolResult => ({
  isError: true,
  content: [{ type: "text", text }],
});

const result = (ok: boolean, text: string): CallToolResult => {
  const truncated =
    text.length > MAX_RESULT_CHARACTERS
      ? `${text.slice(0, MAX_RESULT_CHARACTERS)}\n[Truncated after ${MAX_RESULT_CHARACTERS} characters; narrow the request or page through it.]`
      : text;

  return {
    ...(ok ? {} : { isError: true }),
    content: [{ type: "text", text: truncated || "{}" }],
  };
};
