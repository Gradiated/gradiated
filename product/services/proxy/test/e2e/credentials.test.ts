// Either key can arrive in any header that can hold it: the Gradiated key in
// Authorization, x-api-key or x-gradiated-api-key, and the provider key in
// Authorization or x-api-key. Every placement must route the same way.
import { describe, expect, it } from "vitest";

import { expectPublicError } from "../../../gateway/test/integration/assertions.js";
import { useCases, type Case } from "../../../gateway/test/integration/case.js";
import type { Headers } from "../../../gateway/test/integration/http-client.js";
import {
  anthropicKey,
  CHAT,
  expectProxyError,
  openAiKey,
  providerModel,
  useProxy,
  type ProviderName,
} from "./support/fixtures.js";

const { makeCase } = useCases();
const fixture = useProxy(makeCase);

type Slot = "authorization" | "x-api-key" | "x-gradiated-api-key";

const put = (slot: Slot, key: string): Headers =>
  slot === "authorization"
    ? { authorization: `Bearer ${key}` }
    : { [slot]: key };

interface Placement {
  readonly name: string;
  readonly gradiated: Slot;
  readonly provider?: {
    readonly slot: Exclude<Slot, "x-gradiated-api-key">;
    readonly name: ProviderName;
  };
}

const PLACEMENTS: Placement[] = [
  { name: "Gradiated key in Authorization", gradiated: "authorization" },
  { name: "Gradiated key in x-api-key", gradiated: "x-api-key" },
  {
    name: "Gradiated key in x-gradiated-api-key",
    gradiated: "x-gradiated-api-key",
  },
  ...(["anthropic", "openai"] as const).flatMap((provider): Placement[] => [
    {
      name: `Gradiated key in Authorization, ${provider} key in x-api-key`,
      gradiated: "authorization",
      provider: { slot: "x-api-key", name: provider },
    },
    {
      name: `Gradiated key in x-api-key, ${provider} key in Authorization`,
      gradiated: "x-api-key",
      provider: { slot: "authorization", name: provider },
    },
    {
      name: `Gradiated key in x-gradiated-api-key, ${provider} key in Authorization`,
      gradiated: "x-gradiated-api-key",
      provider: { slot: "authorization", name: provider },
    },
    {
      name: `Gradiated key in x-gradiated-api-key, ${provider} key in x-api-key`,
      gradiated: "x-gradiated-api-key",
      provider: { slot: "x-api-key", name: provider },
    },
  ]),
];

interface Placed {
  readonly headers: Headers;
  readonly providerKey?: string;
}

const place = (instance: Case, placement: Placement): Placed => {
  const providerKey = placement.provider
    ? placement.provider.name === "anthropic"
      ? anthropicKey()
      : openAiKey()
    : undefined;

  return {
    headers: {
      ...put(placement.gradiated, instance.key),
      ...(placement.provider && providerKey
        ? put(placement.provider.slot, providerKey)
        : {}),
    },
    ...(providerKey ? { providerKey } : {}),
  };
};

describe.each(PLACEMENTS)("$name", (placement) => {
  it("serves a hosted model through the gateway and never forwards a provider key", async () => {
    const instance = await fixture.hostedCase();
    const { headers, providerKey } = place(instance, placement);

    const response = await fixture.proxy.client.post(CHAT.path, {
      headers,
      json: CHAT.body(instance.model),
    });

    expect(response.status, response.text).toBe(200);
    await instance.settled(response);
    expect(fixture.provider.requests).toEqual([]);
    if (providerKey)
      expect(JSON.stringify(instance.runtimes[0]!.headers)).not.toContain(
        providerKey,
      );
  });

  if (placement.provider) {
    const { slot, name } = placement.provider;

    it(`relays a model we do not host to ${name} with the key where the client put it`, async () => {
      const instance = await makeCase("vllm");
      const { headers, providerKey } = place(instance, placement);

      const response = await fixture.proxy.client.post(CHAT.path, {
        headers,
        json: CHAT.body(providerModel(name)),
      });

      expect(response.status, response.text).toBe(200);
      const [sent] = fixture.provider.requests;
      expect(sent!.headers[slot]).toBe(
        slot === "authorization" ? `Bearer ${providerKey}` : providerKey,
      );
      expect(JSON.stringify(sent!.headers)).not.toContain(instance.key);
      expect(sent!.headers).not.toHaveProperty(
        slot === "authorization" ? "x-api-key" : "authorization",
      );
      await instance.expectNotDispatched();
    });
  } else {
    it("sends a model we do not host to the gateway, which refuses it", async () => {
      const instance = await makeCase("vllm");
      const { headers } = place(instance, placement);

      const response = await fixture.proxy.client.post(CHAT.path, {
        headers,
        json: CHAT.body(providerModel("openai")),
      });

      expectPublicError(response, { code: "model_not_found", param: "model" });
      expect(fixture.provider.requests).toEqual([]);
      await instance.expectNotDispatched();
    });
  }
});

describe("the same Gradiated key in two headers", () => {
  it.each<[Slot, Slot]>([
    ["authorization", "x-gradiated-api-key"],
    ["x-api-key", "x-gradiated-api-key"],
    ["authorization", "x-api-key"],
  ])("is accepted in %s and %s", async (first, second) => {
    const instance = await fixture.hostedCase();

    const response = await fixture.proxy.client.post(CHAT.path, {
      headers: { ...put(first, instance.key), ...put(second, instance.key) },
      json: CHAT.body(instance.model),
    });

    expect(response.status, response.text).toBe(200);
    await instance.settled(response);
  });
});

describe("the Bearer scheme in any letter case", () => {
  const SCHEMES = ["bearer", "BEARER", "BeArEr"];

  it.each(SCHEMES)("serves a hosted model with %s", async (scheme) => {
    const instance = await fixture.hostedCase();

    const response = await fixture.proxy.client.post(CHAT.path, {
      headers: { authorization: `${scheme} ${instance.key}` },
      json: CHAT.body(instance.model),
    });

    expect(response.status, response.text).toBe(200);
    await instance.settled(response);
  });

  it.each(SCHEMES)(
    "relays a provider key with %s exactly as sent",
    async (scheme) => {
      const instance = await makeCase("vllm");
      const authorization = `${scheme} ${openAiKey()}`;

      const response = await fixture.proxy.client.post(CHAT.path, {
        headers: { authorization, "x-gradiated-api-key": instance.key },
        json: CHAT.body(providerModel("openai")),
      });

      expect(response.status, response.text).toBe(200);
      expect(fixture.provider.requests[0]!.headers.authorization).toBe(
        authorization,
      );
    },
  );
});

describe("refused credentials", () => {
  const otherKey = `grad_${"b".repeat(32)}`;

  it.each<{
    name: string;
    headers: (instance: Case) => Headers;
    format: ProviderName;
  }>([
    ...(["authorization", "x-api-key"] as const).flatMap((slot) => [
      {
        name: `an Anthropic key alone in ${slot}`,
        headers: () => put(slot, anthropicKey()),
        format: "anthropic" as const,
      },
      {
        name: `an OpenAI key alone in ${slot}`,
        headers: () => put(slot, openAiKey()),
        format: "openai" as const,
      },
    ]),
    ...(
      [
        ["authorization", "x-gradiated-api-key"],
        ["x-api-key", "x-gradiated-api-key"],
        ["authorization", "x-api-key"],
      ] as const
    ).map(([first, second]) => ({
      name: `different Gradiated keys in ${first} and ${second}`,
      headers: (instance: Case) => ({
        ...put(first, instance.key),
        ...put(second, otherKey),
      }),
      format: "openai" as const,
    })),
    {
      name: "two provider keys",
      headers: (instance: Case) => ({
        ...put("authorization", openAiKey()),
        ...put("x-api-key", anthropicKey()),
        ...put("x-gradiated-api-key", instance.key),
      }),
      format: "openai" as const,
    },
    ...(
      [
        ["an OpenRouter key", "sk-or-v1-0123456789abcdef0123456789abcdef"],
        ["a DeepSeek key", "sk-0123456789abcdef0123456789abcdef"],
      ] as const
    ).flatMap(([name, key]) =>
      (["authorization", "x-api-key"] as const).map((slot) => ({
        name: `${name} in ${slot}`,
        headers: (instance: Case) => ({
          ...put(slot, key),
          ...put("x-gradiated-api-key", instance.key),
        }),
        format: "openai" as const,
      })),
    ),
    {
      name: "a provider key in x-gradiated-api-key",
      headers: () => put("x-gradiated-api-key", anthropicKey()),
      format: "openai" as const,
    },
  ])(
    "refuses $name before any upstream sees it",
    async ({ headers, format }) => {
      const instance = await fixture.hostedCase();

      const response = await fixture.proxy.client.post(CHAT.path, {
        headers: headers(instance),
        json: CHAT.body(providerModel("openai")),
      });

      expectProxyError(response, "invalid_api_key", format);
      expect(fixture.provider.requests).toEqual([]);
      await instance.expectNotDispatched();
    },
  );

  it.each(["authorization", "x-api-key", "x-gradiated-api-key"] as const)(
    "refuses a revoked Gradiated key in %s beside a provider key",
    async (slot) => {
      const instance = await makeCase("vllm");
      await instance.writeCredentialRow({ revokedAt: new Date() });
      const providerSlot =
        slot === "authorization" ? "x-api-key" : "authorization";

      const response = await fixture.proxy.client.post(CHAT.path, {
        headers: {
          ...put(slot, instance.key),
          ...put(providerSlot, openAiKey()),
        },
        json: CHAT.body(providerModel("openai")),
      });

      expectProxyError(response, "invalid_api_key");
      expect(fixture.provider.requests).toEqual([]);
    },
  );
});
