// The official TypeSafe SDK through the customer-facing proxy: SystemOne is
// served and billed by the gateway behind it, never relayed to a provider.
import {
  AuthenticationError,
  choice,
  NotFoundError,
  noul,
  score,
  TypeSafeError,
} from "@typesafe-ai/sdk";
import { describe, expect, it } from "vitest";

import { useCases } from "../../../../gateway/test/integration/case.js";
import {
  expectSdkError,
  headerRecord,
  rejection,
  typesafeClient,
} from "../../../../gateway/test/integration/typesafe.js";
import { anthropicKey, openAiKey, useProxy } from "../support/fixtures.js";

const { makeCase } = useCases();
const fixture = useProxy(makeCase);

const hostedKev = () => fixture.hostedCase({}, "kev");

const QUESTIONS = {
  billing: noul("Is this about billing?"),
  team: choice("Choose the team.", { billing: null, technical: null }),
  urgency: score("Rate the urgency.", ["Can wait", "Today"]),
};

describe("TypeSafe SDK against a hosted SystemOne model", () => {
  it("answers through the proxy, served and billed by the gateway", async () => {
    const instance = await hostedKev();

    const { data, response } = await typesafeClient(
      instance,
      {},
      fixture.proxy.url,
    )
      .systemOne({ state: { ticket: "Charged twice" }, questions: QUESTIONS })
      .withResponse();

    expect(data.model).toBe(instance.model);
    expect(data.answers.billing.noul).toBe(0.75);
    expect(data.answers.team.choice).toBe("billing");
    expect(data.answers.urgency.legend).toEqual({ 0: "Can wait", 1: "Today" });
    expect(data.usage).toEqual({
      input_tokens: 100,
      cached_input_tokens: 0,
      output_tokens: 0,
    });
    expect(fixture.provider.requests).toEqual([]);
    expect(instance.runtimes[0]!.calls).toHaveLength(1);
    await instance.settled(
      { headers: headerRecord(response.headers) },
      { charge: 1000 },
    );
  });

  it.each([
    {
      name: "an OpenAI key as the SDK's key",
      client: (key: string, gradiated: string) => ({
        apiKey: key,
        defaultHeaders: { "x-gradiated-api-key": gradiated },
      }),
      key: openAiKey,
    },
    {
      name: "an Anthropic key beside the Gradiated key",
      client: (key: string, gradiated: string) => ({
        apiKey: gradiated,
        defaultHeaders: { "x-api-key": key },
      }),
      key: anthropicKey,
    },
  ])(
    "never lets $name reach the runtime or a provider",
    async ({ client, key }) => {
      const instance = await hostedKev();
      const providerKey = key();

      const { data, response } = await typesafeClient(
        instance,
        client(providerKey, instance.key),
        fixture.proxy.url,
      )
        .systemOne({ state: "Synthetic ticket", questions: QUESTIONS })
        .withResponse();

      expect(data.answers.billing.noul).toBe(0.75);
      expect(fixture.provider.requests).toEqual([]);
      expect(JSON.stringify(instance.runtimes[0]!.headers)).not.toContain(
        providerKey,
      );
      expect(JSON.stringify(instance.runtimes[0]!.calls)).not.toContain(
        providerKey,
      );
      await instance.settled(
        { headers: headerRecord(response.headers) },
        { charge: 1000 },
      );
    },
  );

  it("raises AuthenticationError for an unknown Gradiated key", async () => {
    const instance = await hostedKev();

    const error = await rejection(
      typesafeClient(
        instance,
        { apiKey: `grad_${"0".repeat(32)}` },
        fixture.proxy.url,
      ).systemOne({ state: "Synthetic ticket", questions: QUESTIONS }),
    );

    expectSdkError(error, AuthenticationError, {
      status: 401,
      code: "invalid_api_key",
    });
    expect(fixture.provider.requests).toEqual([]);
    await instance.expectNotDispatched();
  });

  it("raises NotFoundError for a model the gateway does not host", async () => {
    const instance = await hostedKev();

    const error = await rejection(
      typesafeClient(instance, {}, fixture.proxy.url).systemOne({
        model: `test/missing-${crypto.randomUUID()}`,
        state: "Synthetic ticket",
        questions: QUESTIONS,
      }),
    );

    expectSdkError(error, NotFoundError, {
      status: 404,
      code: "model_not_found",
    });
    expect(fixture.provider.requests).toEqual([]);
    await instance.expectNotDispatched();
  });

  // KNOWN GAP: TypeSafe's `GET /v1/models` returns `{ models: [...] }`, the
  // gateway returns OpenAI's `{ object: "list", data: [...] }`, so the SDK's
  // `models.list()` cannot read our catalog. When the gateway serves both
  // shapes, replace this with an assertion that the SDK lists the model.
  it("known gap: models.list() cannot read the gateway's catalog", async () => {
    const instance = await hostedKev();

    const listing = await fetch(`${fixture.proxy.url}/v1/models`, {
      headers: { Authorization: `Bearer ${instance.key}` },
    });
    expect(listing.status).toBe(200);
    const body = (await listing.json()) as { data: { id: string }[] };
    expect(body.data.map((model) => model.id)).toContain(instance.model);
    expect(body).not.toHaveProperty("models");

    const error = await rejection(
      typesafeClient(instance, {}, fixture.proxy.url).models.list(),
    );
    expect(error).toBeInstanceOf(TypeSafeError);
    expect((error as Error).message).toMatch(
      /expected \{ models: \[\.\.\.\] \}/,
    );
  });
});
