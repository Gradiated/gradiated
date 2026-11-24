import { afterAll, afterEach, beforeAll, expect, inject } from "vitest";

import type {
  Case,
  CaseOptions,
} from "../../../../gateway/test/integration/case.js";
import type {
  Headers,
  Response,
} from "../../../../gateway/test/integration/http-client.js";
import type { JsonObject } from "../../../../gateway/test/integration/json.js";
import type { RuntimeKind } from "../../../../gateway/test/integration/mock-runtimes/server.js";
import { Link } from "./link.js";
import { MockProvider } from "./provider.js";
import { ProxyProcess } from "./proxy-process.js";

const random = (): string => crypto.randomUUID().replaceAll("-", "");

export const anthropicKey = (): string => `sk-ant-api03-${random()}`;
export const openAiKey = (): string => `sk-proj-${random()}`;

export type ProviderName = "anthropic" | "openai";

export const providerModel = (provider: ProviderName): string =>
  provider === "anthropic" ? `claude-${random()}` : `gpt-${random()}`;

export const providerKey = (provider: ProviderName): string =>
  provider === "anthropic" ? anthropicKey() : openAiKey();

/** The header each provider's SDK puts its own key in. */
export const providerKeyHeaders = (
  provider: ProviderName,
  key: string,
): Headers =>
  provider === "anthropic"
    ? { "x-api-key": key }
    : { authorization: `Bearer ${key}` };

export interface RelayRoute {
  readonly name: string;
  readonly path: string;
  readonly provider: ProviderName;
  readonly providerPath: string;
  readonly body: (model: string) => JsonObject;
}

const messages = (model: string): JsonObject => ({
  model,
  max_tokens: 16,
  messages: [{ role: "user", content: "Synthetic ticket" }],
});

const chat = (model: string): JsonObject => ({
  model,
  messages: [{ role: "user", content: "Synthetic ticket" }],
});

const responses = (model: string): JsonObject => ({
  model,
  input: "Synthetic ticket",
});

export const RELAY_ROUTES: readonly RelayRoute[] = [
  {
    name: "Anthropic Messages",
    path: "/v1/messages",
    provider: "anthropic",
    providerPath: "/v1/messages",
    body: messages,
  },
  {
    name: "Anthropic token counting",
    path: "/v1/messages/count_tokens",
    provider: "anthropic",
    providerPath: "/v1/messages/count_tokens",
    body: messages,
  },
  {
    name: "OpenAI Chat Completions",
    path: "/v1/chat/completions",
    provider: "openai",
    providerPath: "/v1/chat/completions",
    body: chat,
  },
  {
    name: "OpenAI Responses",
    path: "/v1/responses",
    provider: "openai",
    providerPath: "/v1/responses",
    body: responses,
  },
  {
    name: "unprefixed Anthropic Messages",
    path: "/messages",
    provider: "anthropic",
    providerPath: "/v1/messages",
    body: messages,
  },
  {
    name: "unprefixed OpenAI Chat Completions",
    path: "/chat/completions",
    provider: "openai",
    providerPath: "/v1/chat/completions",
    body: chat,
  },
];

export const route = (name: string): RelayRoute => {
  const found = RELAY_ROUTES.find((candidate) => candidate.name === name);
  if (!found) throw new Error(`no relay route named ${name}`);

  return found;
};

export const MESSAGES = route("Anthropic Messages");
export const CHAT = route("OpenAI Chat Completions");

/** Headers for a relay: the provider key in its SDK header and the Gradiated key beside it. */
export const relayHeaders = (
  instance: Case,
  provider: ProviderName,
  key = providerKey(provider),
): Headers => ({
  ...providerKeyHeaders(provider, key),
  "x-gradiated-api-key": instance.key,
});

export interface ProxyFixtureOptions {
  /** Environment overrides for the proxy process. */
  readonly env?: Record<string, string>;
  /** Route the proxy's database connection through a breakable link. */
  readonly databaseLink?: boolean;
  /** Route the proxy's gateway connection through a breakable link. */
  readonly gatewayLink?: boolean;
}

export interface ExtraProxyOptions {
  readonly database?: Link;
  readonly gateway?: Link;
  /** Wait for readiness before returning. Defaults to true. */
  readonly ready?: boolean;
}

export interface ProxyFixture {
  /** A tenant with a hosted model that the proxy's catalog already holds. */
  hostedCase(options?: CaseOptions, kind?: RuntimeKind): Promise<Case>;
  /**
   * Another proxy process with the same upstreams and some settings changed. It
   * stops after the current test.
   */
  startProxy(
    env: Record<string, string>,
    options?: ExtraProxyOptions,
  ): Promise<ProxyProcess>;
  readonly proxy: ProxyProcess;
  readonly provider: MockProvider;
  readonly database: Link;
  readonly gateway: Link;
  readonly gatewayUrl: string;
}

/**
 * One proxy process and mock provider for a test file, in front of the shared
 * gateway stack. After each test the provider must have seen no contract error.
 */
export const useProxy = (
  makeCase: (kind: RuntimeKind, options?: CaseOptions) => Promise<Case>,
  options: ProxyFixtureOptions = {},
): ProxyFixture => {
  let proxy: ProxyProcess | undefined;
  let provider: MockProvider | undefined;
  let database: Link | undefined;
  let gateway: Link | undefined;
  let gatewayUrl = "";
  let databaseUrl = "";
  const extra: ProxyProcess[] = [];

  const logName = (): string =>
    `proxy-${expect.getState().testPath?.split("/").pop() ?? "suite"}-${random().slice(0, 8)}`;

  beforeAll(async () => {
    const stack = inject("stack");
    gatewayUrl = stack.gatewayUrl;
    provider = await MockProvider.start();

    databaseUrl = stack.databaseUrl;
    let proxiedDatabase = databaseUrl;
    if (options.databaseLink) {
      database = await Link.to(databaseUrl);
      proxiedDatabase = database.rewrite(databaseUrl);
    }

    let proxiedGateway = stack.gatewayUrl;
    if (options.gatewayLink) {
      gateway = await Link.to(stack.gatewayUrl);
      proxiedGateway = gateway.rewrite(stack.gatewayUrl);
    }

    proxy = await ProxyProcess.start({
      gatewayUrl: proxiedGateway,
      databaseUrl: proxiedDatabase,
      providerUrl: provider.url,
      logName: logName(),
      env: options.env ?? {},
    });
  });

  afterEach(async () => {
    await Promise.all(extra.splice(0).map((process) => process.stop()));
    database?.set("up");
    gateway?.set("up");
    if (!provider) return;

    const errors = [...provider.errors];
    provider.reset();
    expect(errors, "mock provider contract errors").toEqual([]);
  });

  afterAll(async () => {
    await proxy?.stop();
    await provider?.close();
    await database?.close();
    await gateway?.close();
  });

  const required = <T>(value: T | undefined, name: string): T => {
    if (value === undefined)
      throw new Error(`the proxy fixture has no ${name}`);

    return value;
  };

  return {
    async hostedCase(options, kind = "vllm") {
      const instance = await makeCase(kind, options);
      // Only a load that starts after the model row is committed can contain it.
      await required(proxy, "proxy").catalogRefreshedAfter(Date.now());

      return instance;
    },
    async startProxy(env, { database, gateway, ready = true } = {}) {
      const started = await ProxyProcess.spawn({
        gatewayUrl: gateway ? gateway.rewrite(gatewayUrl) : gatewayUrl,
        databaseUrl: database ? database.rewrite(databaseUrl) : databaseUrl,
        providerUrl: required(provider, "provider").url,
        logName: logName(),
        env,
      });
      extra.push(started);
      if (ready) await started.ready();

      return started;
    },
    get proxy() {
      return required(proxy, "proxy");
    },
    get provider() {
      return required(provider, "provider");
    },
    get database() {
      return required(database, "database link");
    },
    get gateway() {
      return required(gateway, "gateway link");
    },
    get gatewayUrl() {
      return gatewayUrl;
    },
  };
};

/** Errors the proxy answers itself. SDKs branch on status and type, so both are pinned. */
const PROXY_ERRORS = {
  invalid_request: { status: 400, type: "invalid_request_error" },
  invalid_api_key: { status: 401, type: "authentication_error" },
  workspace_archived: { status: 403, type: "permission_error" },
  organization_suspended: { status: 403, type: "permission_error" },
  not_found: { status: 404, type: "invalid_request_error" },
  payload_too_large: { status: 413, type: "invalid_request_error" },
  request_timeout: { status: 408, type: "invalid_request_error" },
  gateway_unavailable: { status: 502, type: "api_error" },
  provider_unavailable: { status: 502, type: "api_error" },
  serving_state_unavailable: { status: 503, type: "api_error" },
  proxy_overloaded: { status: 503, type: "api_error" },
  gateway_timeout: { status: 504, type: "api_error" },
  provider_timeout: { status: 504, type: "api_error" },
} as const;

export type ProxyErrorCode = keyof typeof PROXY_ERRORS;

export const expectProxyError = (
  response: Response,
  code: ProxyErrorCode,
  protocol: ProviderName = "openai",
): void => {
  const { status, type } = PROXY_ERRORS[code];

  expect(response.status, response.text).toBe(status);
  expect(response.error()).toMatchObject({ code, type });
  if (protocol === "anthropic") {
    expect(response.json().type).toBe("error");
  } else {
    expect(response.json()).not.toHaveProperty("type");
  }
};
