// The official TypeSafe SDK (`@typesafe-ai/sdk`) against the real gateway's
// `/v1/systemone`, the way a customer integrates. The mock Kev runtime answers
// deterministically: noul 0.75, the first choice option and score 0.
import {
  APIConnectionError,
  APIError,
  APITimeoutError,
  APIUserAbortError,
  AuthenticationError,
  BadRequestError,
  choice,
  InternalServerError,
  NotFoundError,
  noul,
  PermissionDeniedError,
  RateLimitError,
  score,
  TypeSafeError,
  VERSION,
  type NoulQuestion,
  type SystemOneRequest,
} from "@typesafe-ai/sdk";
import { SystemOneResponseSchema } from "@gradiated/contracts";
import { describe, expect, expectTypeOf, it } from "vitest";

import { entered, fillConcurrencyCap } from "./admission.js";
import { expectRejected } from "./assertions.js";
import { useCases, type Case } from "./case.js";
import { deferred } from "./eventually.js";
import { object, type JsonObject, type JsonValue } from "./json.js";
import type { PlanOptions } from "./mock-runtimes/server.js";
import {
  countingFetch,
  expectSdkError,
  headerRecord,
  IMMEDIATE_RETRIES,
  leaseReleased,
  onlySettlement,
  rejection,
  typesafeClient,
} from "./typesafe.js";

const { makeCase } = useCases();

// Mirrors the gateway's MAX_QUESTIONS, MAX_OPTIONS and MAX_REQUEST_BYTES.
const MAX_QUESTIONS = 1024;
const MAX_OPTIONS = 255;
const MAX_REQUEST_BYTES = 32_000_000;
const LARGE_STATE_BYTES = 4 * 1024 * 1024;

// Kev usage is 100 input tokens; the catalog prices 10 per input and 2 per cached token.
const FULL_CHARGE = 1000;
const charge = (cached: number): number => (100 - cached) * 10 + cached * 2;

const TICKET = { ticket: "I was charged twice. Please fix this today." };

const nouls = (count: number): Record<string, NoulQuestion> =>
  Object.fromEntries(
    Array.from({ length: count }, (_, index) => [
      `q${index}`,
      noul(`Question ${index}?`),
    ]),
  );

const options = (count: number): Record<string, null> =>
  Object.fromEntries(
    Array.from({ length: count }, (_, index) => [`option-${index}`, null]),
  );

const sum = (values: Record<string, number>): number =>
  Object.values(values).reduce((total, value) => total + value, 0);

/** An arbitrary request the SDK forwards as is: it copies unknown properties. */
const loose = (fields: Record<string, unknown>): SystemOneRequest =>
  ({
    state: TICKET,
    questions: { q: noul("Is this billing?") },
    ...fields,
  }) as SystemOneRequest;

const settledFrom = (
  instance: Case,
  error: APIError,
  options: Parameters<Case["settled"]>[1],
): Promise<JsonObject> =>
  instance.settled({ headers: headerRecord(error.headers) }, options);

describe("TypeSafe SDK answers", () => {
  it.each([0, 40])(
    "answers every question type with typed results (cached=%i)",
    async (cached) => {
      const instance = await makeCase("kev");
      instance.runtimes[0]!.enqueue({ cached });

      const { data, response, requestId } = await typesafeClient(instance)
        .systemOne({
          state: TICKET,
          questions: {
            yes: noul("Is this a ticket?", {
              true: "A support ticket",
              false: "Anything else",
            }),
            team: choice("Choose the team.", {
              billing: "Charges or payments",
              sales: null,
            }),
            level: score("Rate the urgency.", ["Can wait", "Today", "Now"]),
          },
        })
        .withResponse();

      expectTypeOf(data.answers.yes.noul).toEqualTypeOf<number>();
      expectTypeOf(data.answers.team.choice).toEqualTypeOf<
        "billing" | "sales"
      >();
      expectTypeOf(data.answers.level.legend).toHaveProperty("2");

      expect(data.answers.yes).toEqual({ type: "noul", noul: 0.75 });
      expect(data.answers.team).toEqual({
        type: "choice",
        choice: "billing",
        confidence: 1,
        probabilities: { billing: 1, sales: 0 },
      });
      expect(data.answers.level).toEqual({
        type: "score",
        score: 0,
        confidence: 1,
        probabilities: { 0: 1, 1: 0, 2: 0 },
        legend: { 0: "Can wait", 1: "Today", 2: "Now" },
      });
      expect(sum(data.answers.team.probabilities)).toBeCloseTo(1);
      expect(sum(data.answers.level.probabilities)).toBeCloseTo(1);
      expect(data.usage).toEqual({
        input_tokens: 100,
        cached_input_tokens: cached,
        output_tokens: 0,
      });
      expect(SystemOneResponseSchema.safeParse(data).success).toBe(true);

      // The public model ID is written back over the runtime's private name.
      expect(data.model).toBe(instance.model);
      const sent = instance.runtimes[0]!.calls[0]!;
      expect(sent.model).toBe(instance.runtimeModel);
      expect(sent.state).toEqual(TICKET);
      expect(object(sent.questions).yes).toEqual({
        type: "noul",
        instructions: "Is this a ticket?",
        criteria: { true: "A support ticket", false: "Anything else" },
      });

      expect(response.status).toBe(200);
      expect(response.headers.get("x-gradiated-service-tier")).toBe("default");
      expect(response.headers.get("x-gradiated-generation-id")).toMatch(
        /^[0-9a-f-]{36}$/,
      );
      // TypeSafe's request ID header is not part of the gateway's contract.
      expect(requestId).toBeUndefined();

      const properties = await instance.settled(
        { headers: headerRecord(response.headers) },
        { charge: charge(cached) },
      );
      expect(properties.usage).toMatchObject({
        input_tokens: 100,
        cached_input_tokens: cached,
        output_tokens: 0,
      });
    },
  );

  it("sends the SDK's own headers to the gateway but none of them to the runtime", async () => {
    const instance = await makeCase("kev");
    const { fetch, attempts } = countingFetch();

    await typesafeClient(instance, { fetch }).systemOne({
      state: "Synthetic ticket",
      questions: { q: noul("Is this billing?") },
    });

    expect(attempts).toHaveLength(1);
    expect(attempts[0]!.url).toBe(
      new URL("/v1/systemone", instance.http.baseUrl).href,
    );
    expect(attempts[0]!.headers.get("x-typesafe-sdk")).toBe(
      `typesafe-sdk/${VERSION}`,
    );
    const runtimeHeaders = instance.runtimes[0]!.headers[0]!;
    expect(JSON.stringify(runtimeHeaders)).not.toContain(instance.key);
    expect(
      Object.keys(runtimeHeaders).filter((name) =>
        name.startsWith("x-typesafe"),
      ),
    ).toEqual([]);
  });

  it("keeps an optional latency the runtime reports", async () => {
    const instance = await makeCase("kev");
    instance.runtimes[0]!.enqueue({
      mutateBody: (body) => {
        body.latency_ms = 12.5;
      },
    });

    const data = await typesafeClient(instance).systemOne({
      state: "Synthetic ticket",
      questions: { q: noul("Is this billing?") },
    });

    expect(data).toMatchObject({ latency_ms: 12.5 });
  });

  it("lets a call override the default model", async () => {
    const instance = await makeCase("kev");

    const data = await typesafeClient(instance, {
      defaultModel: "jev-latest",
    }).systemOne({
      model: instance.model,
      state: "Synthetic ticket",
      questions: { q: noul("Is this billing?") },
    });

    expect(data.model).toBe(instance.model);
  });
});

describe("TypeSafe SDK request bounds", () => {
  it.each([1, 64, 65, MAX_QUESTIONS])(
    "accepts %i questions in one request",
    async (count) => {
      const instance = await makeCase("kev");

      const { data, response } = await typesafeClient(instance)
        .systemOne({ state: TICKET, questions: nouls(count) })
        .withResponse();

      expect(Object.keys(data.answers)).toHaveLength(count);
      expect(Object.values(data.answers).every((a) => a.noul === 0.75)).toBe(
        true,
      );
      expect(
        Object.keys(object(instance.runtimes[0]!.calls[0]!.questions)),
      ).toHaveLength(count);
      // One request is one generation, whatever its question count.
      await instance.settled(
        { headers: headerRecord(response.headers) },
        { charge: FULL_CHARGE },
      );
    },
  );

  it(`rejects ${MAX_QUESTIONS + 1} questions as a bad request`, async () => {
    const instance = await makeCase("kev");

    const error = await rejection(
      typesafeClient(instance).systemOne({
        state: TICKET,
        questions: nouls(MAX_QUESTIONS + 1),
      }),
    );

    expectSdkError(error, BadRequestError, {
      status: 400,
      code: "invalid_request",
      param: "questions",
    });
    await instance.expectNotDispatched();
  });

  it(`accepts ${MAX_OPTIONS} choice options and rejects ${MAX_OPTIONS + 1}`, async () => {
    const instance = await makeCase("kev");
    const sdk = typesafeClient(instance);

    const data = await sdk.systemOne({
      state: TICKET,
      questions: { pick: choice("Pick one.", options(MAX_OPTIONS)) },
    });
    expect(Object.keys(data.answers.pick.probabilities)).toHaveLength(
      MAX_OPTIONS,
    );
    expect(data.answers.pick.choice).toBe("option-0");

    const error = await rejection(
      sdk.systemOne({
        state: TICKET,
        questions: { pick: choice("Pick one.", options(MAX_OPTIONS + 1)) },
      }),
    );
    expectSdkError(error, BadRequestError, {
      status: 400,
      code: "invalid_request",
      param: "questions",
    });
    expect(instance.runtimes[0]!.calls).toHaveLength(1);
  });

  it("refuses empty questions and one-level scores before sending", async () => {
    const instance = await makeCase("kev");
    const { fetch, attempts } = countingFetch();
    const sdk = typesafeClient(instance, { fetch });

    expect(() => sdk.systemOne({ state: TICKET, questions: {} })).toThrow(
      TypeSafeError,
    );
    expect(() =>
      sdk.systemOne(
        loose({
          questions: { level: { type: "score", criteria: ["Only"] } },
        }),
      ),
    ).toThrow(TypeSafeError);

    expect(attempts).toEqual([]);
    await instance.expectNotDispatched();
  });

  it("still rejects empty questions the SDK is bypassed for", async () => {
    const instance = await makeCase("kev");

    const response = await instance.post({ questions: {} });

    expectRejected(response, { code: "invalid_request", param: "questions" });
    await instance.expectNotDispatched();
  });
});

describe("TypeSafe SDK state", () => {
  it.each<{ name: string; state: JsonValue }>([
    { name: "text", state: "Ticket: I was charged twice ✓ — 二重請求" },
    { name: "an object", state: { ticket: { tags: ["billing"], open: true } } },
    { name: "an array", state: [{ role: "customer", text: "Refund?" }, 3] },
    { name: "an empty string", state: "" },
  ])("forwards $name as the state", async ({ state }) => {
    const instance = await makeCase("kev");

    const data = await typesafeClient(instance).systemOne({
      state: state as string,
      questions: { q: noul("Is this billing?") },
    });

    expect(data.answers.q.noul).toBe(0.75);
    expect(instance.runtimes[0]!.calls[0]!.state).toEqual(state);
  });

  // Kev's own body limit is 1 MiB, so this is four times what any real runtime
  // takes. Forwarding nearly the gateway's 32 MB limit does not fit the shared
  // gateway's 3-second deadline in a debug build, so the suite stops here.
  it("forwards a multi-megabyte state byte for byte", async () => {
    const instance = await makeCase("kev");
    const state = "Synthetic ✓ ".repeat(Math.floor(LARGE_STATE_BYTES / 12));

    const data = await typesafeClient(instance, { timeout: 20_000 }).systemOne({
      state,
      questions: { q: noul("Is this billing?") },
    });

    expect(data.answers.q.noul).toBe(0.75);
    expect(instance.runtimes[0]!.calls[0]!.state === state).toBe(true);
  });

  it("rejects a body over the limit as 413 without dispatching", async () => {
    const instance = await makeCase("kev");

    const error = await rejection(
      typesafeClient(instance, { timeout: 20_000 }).systemOne({
        state: "x".repeat(MAX_REQUEST_BYTES),
        questions: { q: noul("Is this billing?") },
      }),
    );

    // The SDK has no subclass for 413.
    expectSdkError(error, APIError, {
      status: 413,
      code: "payload_too_large",
      exact: true,
    });
    await instance.expectNotDispatched();
  });

  it.each<{ name: string; state: unknown }>([
    { name: "null", state: null },
    { name: "a number", state: 42 },
    { name: "a boolean", state: true },
  ])("rejects $name as the state", async ({ state }) => {
    const instance = await makeCase("kev");

    const error = await rejection(
      typesafeClient(instance).systemOne(loose({ state })),
    );

    expectSdkError(error, BadRequestError, {
      status: 400,
      code: "invalid_request",
      param: "state",
    });
    await instance.expectNotDispatched();
  });

  it.each<{ name: string; fields: Record<string, unknown> }>([
    { name: "a session ID", fields: { session_id: "synthetic-session" } },
    { name: "the default service tier", fields: { service_tier: "default" } },
    {
      name: "both",
      fields: { session_id: "synthetic-session", service_tier: "default" },
    },
  ])("accepts $name without forwarding it", async ({ fields }) => {
    const instance = await makeCase("kev");

    const { data, response } = await typesafeClient(instance)
      .systemOne(loose(fields))
      .withResponse();

    expect(data.answers.q).toEqual({ type: "noul", noul: 0.75 });
    expect(response.headers.get("x-gradiated-service-tier")).toBe("default");
    // The mock rejects any field beyond model, state, questions and priority.
    expect(instance.runtimes[0]!.calls[0]).toMatchObject({ priority: 0 });
    await instance.settled(
      { headers: headerRecord(response.headers) },
      { charge: FULL_CHARGE },
    );
  });

  it.each<{
    name: string;
    fields: Record<string, unknown>;
    code: string;
    param: string | null;
  }>([
    {
      name: "the fast tier",
      fields: { service_tier: "fast" },
      code: "unsupported_parameter",
      param: "service_tier",
    },
    {
      name: "the flex tier",
      fields: { service_tier: "flex" },
      code: "unsupported_parameter",
      param: "service_tier",
    },
    {
      name: "the priority tier",
      fields: { service_tier: "priority" },
      code: "invalid_request",
      param: null,
    },
    {
      name: "a priority",
      fields: { priority: 0 },
      code: "invalid_request",
      param: null,
    },
    {
      name: "streaming",
      fields: { stream: true },
      code: "invalid_request",
      param: null,
    },
    {
      name: "a token limit",
      fields: { max_tokens: 1 },
      code: "invalid_request",
      param: null,
    },
    {
      name: "an unknown field",
      fields: { unknown_synthetic_field: "x" },
      code: "invalid_request",
      param: null,
    },
    {
      name: "a null session ID",
      fields: { session_id: null },
      code: "invalid_request",
      param: null,
    },
    {
      name: "an empty session ID",
      fields: { session_id: "" },
      code: "invalid_request",
      param: "session_id",
    },
    {
      name: "an unknown question field",
      fields: {
        questions: { q: { type: "noul", instructions: "x", weight: 2 } },
      },
      code: "invalid_request",
      param: "questions",
    },
    {
      name: "an unknown question type",
      fields: { questions: { q: { type: "rank", instructions: "x" } } },
      code: "invalid_request",
      param: "questions",
    },
    {
      name: "an unknown noul outcome",
      fields: {
        questions: {
          q: { type: "noul", instructions: "x", criteria: { maybe: "?" } },
        },
      },
      code: "invalid_request",
      param: "questions",
    },
  ])(
    "rejects $name as a bad request without dispatching",
    async ({ fields, code, param }) => {
      const instance = await makeCase("kev");

      const error = await rejection(
        typesafeClient(instance).systemOne(loose(fields)),
      );

      expectSdkError(error, BadRequestError, { status: 400, code, param });
      await instance.expectNotDispatched();
    },
  );
});

describe("TypeSafe SDK errors", () => {
  it("raises AuthenticationError for an unknown key", async () => {
    const instance = await makeCase("kev");

    const error = await rejection(
      typesafeClient(instance, { apiKey: `grad_${"0".repeat(32)}` }).systemOne({
        state: TICKET,
        questions: { q: noul("Is this billing?") },
      }),
    );

    expectSdkError(error, AuthenticationError, {
      status: 401,
      code: "invalid_api_key",
    });
    await instance.expectNotDispatched();
  });

  it("raises NotFoundError for an unknown model", async () => {
    const instance = await makeCase("kev");

    const error = await rejection(
      typesafeClient(instance).systemOne({
        model: `test/missing-${crypto.randomUUID()}`,
        state: TICKET,
        questions: { q: noul("Is this billing?") },
      }),
    );

    expectSdkError(error, NotFoundError, {
      status: 404,
      code: "model_not_found",
      param: "model",
    });
    await instance.expectNotDispatched();
  });

  it.each([
    { name: "a suspended organization", code: "organization_suspended" },
    { name: "an archived workspace", code: "workspace_archived" },
  ] as const)("raises PermissionDeniedError for $name", async ({ code }) => {
    const instance = await makeCase("kev");
    await instance.setTenant(
      code === "organization_suspended"
        ? { organizationStatus: "suspended" }
        : { workspaceArchived: true },
    );

    const error = await rejection(
      typesafeClient(instance).systemOne({
        state: TICKET,
        questions: { q: noul("Is this billing?") },
      }),
    );

    expectSdkError(error, PermissionDeniedError, { status: 403, code });
    await instance.expectNotDispatched();
  });

  it("raises a plain APIError for an exhausted prepaid balance", async () => {
    const instance = await makeCase("kev");
    await instance.setTenant({ balance: 0 });

    const error = await rejection(
      typesafeClient(instance).systemOne({
        state: TICKET,
        questions: { q: noul("Is this billing?") },
      }),
    );

    // The SDK has no subclass for 402.
    expectSdkError(error, APIError, {
      status: 402,
      code: "insufficient_balance",
      exact: true,
    });
    await instance.expectNotDispatched();
  });

  it("raises RateLimitError at the organization's concurrency cap", async () => {
    const instance = await makeCase("kev");
    const held = await fillConcurrencyCap(instance);

    try {
      const error = await rejection(
        typesafeClient(instance).systemOne({
          state: TICKET,
          questions: { q: noul("Is this billing?") },
        }),
      );

      expectSdkError(error, RateLimitError, {
        status: 429,
        code: "concurrency_exceeded",
      });
    } finally {
      held.release();
    }
    for (const request of held.requests) {
      expect((await request).status).toBe(200);
    }
  });

  it.each<{
    name: string;
    plan: PlanOptions;
    kind: abstract new (...args: never[]) => APIError;
    status: number;
    code: string;
  }>([
    {
      name: "a runtime 429",
      plan: { status: 429, errorHeaders: { "Retry-After": "7" } },
      kind: RateLimitError,
      status: 429,
      code: "capacity_exceeded",
    },
    {
      name: "a runtime 503 (queue full)",
      plan: { status: 503 },
      kind: RateLimitError,
      status: 429,
      code: "capacity_exceeded",
    },
    {
      name: "a runtime 500",
      plan: { status: 500 },
      kind: InternalServerError,
      status: 503,
      code: "runtime_unavailable",
    },
    {
      name: "a runtime 422 (token limit)",
      plan: { status: 422 },
      kind: BadRequestError,
      status: 400,
      code: "invalid_request",
    },
    {
      name: "a dropped runtime connection",
      plan: { fault: "disconnect" },
      kind: InternalServerError,
      status: 503,
      code: "runtime_unavailable",
    },
    {
      name: "a runtime body that is not JSON",
      plan: { fault: "invalid_json" },
      kind: InternalServerError,
      status: 503,
      code: "runtime_unavailable",
    },
    {
      name: "a choice outside the options",
      plan: {
        mutateBody: (body) => {
          object(object(body.answers).team).choice = "PRIVATE_RUNTIME_DETAIL";
        },
      },
      kind: InternalServerError,
      status: 503,
      code: "runtime_unavailable",
    },
    {
      name: "probabilities that do not sum to one",
      plan: {
        mutateBody: (body) => {
          object(object(body.answers).team).probabilities = {
            billing: 0.5,
            sales: 0.1,
          };
        },
      },
      kind: InternalServerError,
      status: 503,
      code: "runtime_unavailable",
    },
    {
      name: "a missing answer",
      plan: {
        mutateBody: (body) => {
          delete object(body.answers).level;
        },
      },
      kind: InternalServerError,
      status: 503,
      code: "runtime_unavailable",
    },
    {
      name: "a noul above one",
      plan: {
        mutateBody: (body) => {
          object(object(body.answers).yes).noul = 1.5;
        },
      },
      kind: InternalServerError,
      status: 503,
      code: "runtime_unavailable",
    },
    {
      name: "a score legend without text",
      plan: {
        mutateBody: (body) => {
          object(object(body.answers).level).legend = { 0: 1, 1: 2 };
        },
      },
      kind: InternalServerError,
      status: 503,
      code: "runtime_unavailable",
    },
  ])(
    "maps $name to the SDK's error and charges nothing",
    async ({ plan, kind, status, code }) => {
      const instance = await makeCase("kev");
      instance.runtimes[0]!.enqueue(plan);

      const error = await rejection(
        typesafeClient(instance).systemOne({
          state: TICKET,
          questions: {
            yes: noul("Is this a ticket?"),
            team: choice("Choose the team.", { billing: null, sales: null }),
            level: score("Rate the urgency.", ["Low", "High"]),
          },
        }),
      );

      const api = expectSdkError(error, kind, { status, code });
      expect(JSON.stringify(api.body)).not.toContain("PRIVATE_RUNTIME_DETAIL");
      expect(api.message).not.toContain("PRIVATE_RUNTIME_DETAIL");
      await settledFrom(instance, api, { status: "failed", charge: 0 });
      expect(instance.runtimes[0]!.calls).toHaveLength(1);
    },
  );

  // KNOWN GAP, not a regression guard to keep: the gateway sends no Retry-After
  // on any 429 and drops the runtime's, so the SDK's `retryAfterMs` is always
  // undefined and it falls back to its own backoff. When the gateway starts
  // sending one, replace this with an assertion that the SDK honours it.
  it("known gap: a 429 carries no Retry-After for the SDK to honour", async () => {
    const instance = await makeCase("kev");
    instance.runtimes[0]!.enqueue({
      status: 429,
      errorHeaders: { "Retry-After": "7" },
    });

    const error = await rejection(
      typesafeClient(instance).systemOne({
        state: TICKET,
        questions: { q: noul("Is this billing?") },
      }),
    );

    const api = expectSdkError(error, RateLimitError, {
      status: 429,
      code: "capacity_exceeded",
    });
    expect(api.headers.get("retry-after")).toBeNull();
    expect((api as RateLimitError).retryAfterMs).toBeUndefined();
    await settledFrom(instance, api, { status: "failed", charge: 0 });
  });
});

describe("TypeSafe SDK retries", () => {
  it("retries a 429 and a 5xx, then bills only the answer", async () => {
    const instance = await makeCase("kev");
    instance.runtimes[0]!.enqueue({ status: 429 });
    instance.runtimes[0]!.enqueue({ status: 500 });
    const { fetch, attempts } = countingFetch();

    const { data, response } = await typesafeClient(instance, {
      fetch,
      retry: { maxRetries: 2, ...IMMEDIATE_RETRIES },
    })
      .systemOne({ state: TICKET, questions: { q: noul("Is this billing?") } })
      .withResponse();

    expect(data.answers.q.noul).toBe(0.75);
    expect(
      attempts.map((a) => a.headers.get("x-typesafe-retry-count")),
    ).toEqual([null, "1", "2"]);
    expect(instance.runtimes[0]!.calls).toHaveLength(3);

    // Every attempt is its own generation; only the answered one is charged.
    await instance.settled(
      { headers: headerRecord(response.headers) },
      { charge: FULL_CHARGE },
    );
    const rows = await instance.settlements();
    expect(rows.map((row) => row.properties.status).sort()).toEqual([
      "failed",
      "failed",
      "succeeded",
    ]);
    expect(await instance.charged()).toBe(FULL_CHARGE);
  });

  it("gives up after maxRetries and charges nothing", async () => {
    const instance = await makeCase("kev");
    for (let index = 0; index < 3; index += 1) {
      instance.runtimes[0]!.enqueue({ status: 500 });
    }
    const { fetch, attempts } = countingFetch();

    const error = await rejection(
      typesafeClient(instance, {
        fetch,
        retry: { maxRetries: 2, ...IMMEDIATE_RETRIES },
      }).systemOne({
        state: TICKET,
        questions: { q: noul("Is this billing?") },
      }),
    );

    expectSdkError(error, InternalServerError, {
      status: 503,
      code: "runtime_unavailable",
    });
    expect(attempts).toHaveLength(3);
    expect(instance.runtimes[0]!.calls).toHaveLength(3);
    expect(await instance.settlements()).toHaveLength(3);
    expect(await instance.charged()).toBe(0);
  });

  it.each<{
    name: string;
    prepare: (instance: Case) => unknown;
    request: (instance: Case) => SystemOneRequest;
    apiKey?: string;
    kind: abstract new (...args: never[]) => APIError;
    dispatched: number;
  }>([
    {
      name: "an invalid request",
      prepare: () => undefined,
      request: () => loose({ state: null }),
      kind: BadRequestError,
      dispatched: 0,
    },
    {
      name: "an unknown key",
      prepare: () => undefined,
      request: () => loose({}),
      apiKey: `grad_${"0".repeat(32)}`,
      kind: AuthenticationError,
      dispatched: 0,
    },
    {
      name: "an unknown model",
      prepare: () => undefined,
      request: () => loose({ model: `test/missing-${crypto.randomUUID()}` }),
      kind: NotFoundError,
      dispatched: 0,
    },
    {
      name: "a runtime 422",
      prepare: (instance) => instance.runtimes[0]!.enqueue({ status: 422 }),
      request: () => loose({}),
      kind: BadRequestError,
      dispatched: 1,
    },
  ])(
    "does not retry $name",
    async ({ prepare, request, apiKey, kind, dispatched }) => {
      const instance = await makeCase("kev");
      await prepare(instance);
      const { fetch, attempts } = countingFetch();

      const error = await rejection(
        typesafeClient(instance, {
          fetch,
          retry: { maxRetries: 2, ...IMMEDIATE_RETRIES },
          ...(apiKey ? { apiKey } : {}),
        }).systemOne(request(instance)),
      );

      expect(error).toBeInstanceOf(kind);
      expect(attempts).toHaveLength(1);
      expect(instance.runtimes[0]!.calls).toHaveLength(dispatched);
      expect(await instance.charged()).toBe(0);
    },
  );
});

describe("TypeSafe SDK cancellation", () => {
  it("times out, and the gateway cancels the generation without charge", async () => {
    const instance = await makeCase("kev");
    const gate = deferred();
    instance.runtimes[0]!.enqueue({ gate });

    try {
      const error = await rejection(
        typesafeClient(instance, { timeout: 300 }).systemOne({
          state: TICKET,
          questions: { q: noul("Is this billing?") },
        }),
      );

      expect(error).toBeInstanceOf(APITimeoutError);
      expect(error).toBeInstanceOf(APIConnectionError);
      const properties = await onlySettlement(instance);
      expect(properties).toMatchObject({
        status: "cancelled",
        model_id: instance.model,
        usage: { charge: 0 },
        outcome: { cancellation_owner: "client" },
      });
    } finally {
      gate.resolve();
    }
    await leaseReleased(instance);
  });

  it("retries after a timeout and bills only the answered attempt", async () => {
    const instance = await makeCase("kev");
    const gate = deferred();
    instance.runtimes[0]!.enqueue({ gate });
    const { fetch, attempts } = countingFetch();

    try {
      const { data, response } = await typesafeClient(instance, {
        fetch,
        timeout: 300,
        retry: { maxRetries: 1, ...IMMEDIATE_RETRIES },
      })
        .systemOne({ state: TICKET, questions: { q: noul("Is this?") } })
        .withResponse();

      expect(data.answers.q.noul).toBe(0.75);
      expect(attempts).toHaveLength(2);
      await instance.settled(
        { headers: headerRecord(response.headers) },
        { charge: FULL_CHARGE },
      );
    } finally {
      gate.resolve();
    }

    const rows = await instance.settlements();
    expect(rows.map((row) => row.properties.status).sort()).toEqual([
      "cancelled",
      "succeeded",
    ]);
    expect(await instance.charged()).toBe(FULL_CHARGE);
    await leaseReleased(instance);
  });

  it("aborts through an AbortSignal, and the gateway cancels without charge", async () => {
    const instance = await makeCase("kev");
    const gate = deferred();
    const plan = instance.runtimes[0]!.enqueue({ gate });
    const controller = new AbortController();

    try {
      const call = rejection(
        typesafeClient(instance, {
          retry: { maxRetries: 2, ...IMMEDIATE_RETRIES },
        }).systemOne(
          { state: TICKET, questions: { q: noul("Is this billing?") } },
          { signal: controller.signal },
        ),
      );
      await entered(plan);
      controller.abort();

      // A caller's abort is never retried.
      expect(await call).toBeInstanceOf(APIUserAbortError);
      const properties = await onlySettlement(instance);
      expect(properties).toMatchObject({
        status: "cancelled",
        usage: { charge: 0 },
        outcome: { cancellation_owner: "client" },
      });
      expect(instance.runtimes[0]!.calls).toHaveLength(1);
    } finally {
      gate.resolve();
    }
    await leaseReleased(instance);
  });

  it("sends nothing for an already aborted signal", async () => {
    const instance = await makeCase("kev");
    const { fetch, attempts } = countingFetch();

    const error = await rejection(
      typesafeClient(instance, { fetch }).systemOne(
        { state: TICKET, questions: { q: noul("Is this billing?") } },
        { signal: AbortSignal.abort() },
      ),
    );

    expect(error).toBeInstanceOf(APIUserAbortError);
    expect(attempts.length).toBeLessThanOrEqual(1);
    await instance.expectNotDispatched();
  });
});

describe("TypeSafe SDK routing", () => {
  it("refuses a SystemOne request for a chat model", async () => {
    const instance = await makeCase("vllm");

    const error = await rejection(
      typesafeClient(instance).systemOne({
        state: TICKET,
        questions: { q: noul("Is this billing?") },
      }),
    );

    expectSdkError(error, BadRequestError, {
      status: 400,
      code: "unsupported_parameter",
      param: "model",
    });
    await instance.expectNotDispatched();
  });

  it("pins a deployment through the SDK's default and per-call headers", async () => {
    const instance = await makeCase("kev", { replicas: 2 });
    const [first, second] = instance.deployments;
    const header = "x-gradiated-deployment-id";
    const sdk = typesafeClient(instance, {
      defaultHeaders: { [header]: second!.id },
    });
    const request = {
      state: TICKET,
      questions: { q: noul("Is this billing?") },
    };

    const pinned = await sdk.systemOne(request).withResponse();
    const overridden = await sdk
      .systemOne(request, { headers: { [header]: first!.id } })
      .withResponse();

    expect(pinned.response.headers.get(header)).toBe(second!.id);
    expect(overridden.response.headers.get(header)).toBe(first!.id);
    expect(instance.runtimes.map((runtime) => runtime.calls.length)).toEqual([
      1, 1,
    ]);
    for (const { response } of [pinned, overridden]) {
      await instance.settled(
        { headers: headerRecord(response.headers) },
        { charge: FULL_CHARGE },
      );
    }
  });

  it.each([
    { target: "invalid", kind: BadRequestError, status: 400 },
    {
      target: "00000000-0000-0000-0000-000000000000",
      kind: NotFoundError,
      status: 404,
    },
  ])(
    "rejects the deployment target $target",
    async ({ target, kind, status }) => {
      const instance = await makeCase("kev");

      const error = await rejection(
        typesafeClient(instance, {
          defaultHeaders: { "x-gradiated-deployment-id": target },
        }).systemOne({
          state: TICKET,
          questions: { q: noul("Is this billing?") },
        }),
      );

      expect(error).toBeInstanceOf(kind);
      expect((error as APIError).status).toBe(status);
      await instance.expectNotDispatched();
    },
  );

  it.todo(
    "owned model: the owner succeeds and another organization gets NotFoundError (needs #1235, organization-owned models)",
  );
});

// The SDK's `choice()` takes only the object form, so list criteria (PostHog's
// clients send them) go over raw HTTP. The gateway rewrites them to the object
// form before dispatch; the mock runtime rejects lists as kev_http does.
describe("List-form choice criteria", () => {
  const post = (instance: Case, questions: JsonObject) =>
    instance.http.post("/v1/systemone", {
      headers: instance.headers,
      json: { model: instance.model, state: TICKET, questions },
    });

  it("is refused by the SDK itself", () => {
    expect(() => choice("Choose.", ["billing", "technical"] as never)).toThrow(
      TypeSafeError,
    );
  });

  it("answers by label and forwards the object form", async () => {
    const instance = await makeCase("kev");

    const response = await post(instance, {
      team: {
        type: "choice",
        instructions: "Choose the team.",
        criteria: ["technical", "billing", "sales"],
      },
      described: {
        type: "choice",
        instructions: "Choose.",
        criteria: { yes: "Agree", no: null },
      },
      single: { type: "choice", criteria: ["only"] },
      level: {
        type: "score",
        instructions: "Rate the urgency.",
        criteria: ["Low", "High"],
      },
    });

    expect(response.status, response.text).toBe(200);
    const body = response.json();
    expect(SystemOneResponseSchema.safeParse(body).success).toBe(true);
    const answers = object(body.answers);
    expect(answers.team).toEqual({
      type: "choice",
      choice: "technical",
      confidence: 1,
      probabilities: { technical: 1, billing: 0, sales: 0 },
    });
    expect(object(answers.single).choice).toBe("only");

    const sent = object(instance.runtimes[0]!.calls[0]!.questions);
    expect(object(sent.team).criteria).toEqual({
      technical: null,
      billing: null,
      sales: null,
    });
    expect(Object.keys(object(object(sent.team).criteria))).toEqual([
      "technical",
      "billing",
      "sales",
    ]);
    expect(object(sent.described).criteria).toEqual({
      yes: "Agree",
      no: null,
    });
    expect(object(sent.single).criteria).toEqual({ only: null });
    expect(object(sent.level).criteria).toEqual(["Low", "High"]);
    await instance.settled(response, { charge: FULL_CHARGE });
  });

  it(`accepts ${MAX_OPTIONS} labels`, async () => {
    const instance = await makeCase("kev");
    const labels = Object.keys(options(MAX_OPTIONS));

    const response = await post(instance, {
      pick: { type: "choice", criteria: labels },
    });

    expect(response.status, response.text).toBe(200);
    const sent = object(instance.runtimes[0]!.calls[0]!.questions);
    expect(Object.keys(object(object(sent.pick).criteria))).toEqual(labels);
    await instance.settled(response, { charge: FULL_CHARGE });
  });

  it.each<{ name: string; criteria: JsonValue }>([
    { name: "an empty list", criteria: [] },
    {
      name: `${MAX_OPTIONS + 1} labels`,
      criteria: Object.keys(options(MAX_OPTIONS + 1)),
    },
    { name: "duplicate labels", criteria: ["billing", "billing"] },
    { name: "an empty label", criteria: ["billing", ""] },
    { name: "a non-string label", criteria: ["billing", 2] },
    { name: "a nested list", criteria: [["billing"]] },
    { name: "a null label", criteria: ["billing", null] },
  ])("rejects $name without dispatching", async ({ criteria }) => {
    const instance = await makeCase("kev");

    const response = await post(instance, {
      pick: { type: "choice", instructions: "Choose.", criteria },
    });

    expectRejected(response, { code: "invalid_request", param: "questions" });
    await instance.expectNotDispatched();
  });
});
