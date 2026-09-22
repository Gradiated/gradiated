/**
 * Official TypeSafe SDK checks for an already provisioned, isolated local gateway.
 *
 * Run: pnpm test:kev-sdk
 *
 * Integration requires KEV_GATEWAY_BASE_URL (origin, e.g. http://127.0.0.1:3002),
 * KEV_GATEWAY_API_KEY and optional KEV_GATEWAY_MODEL (default jaredpalmer/kev-9b).
 * Configure the key through the environment, never command-line arguments. No
 * production target, registration, key creation or auth mutations are performed.
 * Provision the local gateway and its isolated auth/model/cache fixtures separately.
 * With no URL, only offline harness checks run and integration tests skip.
 *
 * Budgets: at most 20 HTTP attempts, 16 KiB per request, 100,000 observed input
 * tokens, 180 seconds per integration session; no retries, redirects or proxies.
 * Each test has a hard 30-second timeout. Fixtures are small (at most three valid
 * questions), never request generation, and only address literal loopback IPs. The
 * isolated gateway may use the already provisioned paid GPU runtime; this suite
 * never rents new hardware. These limits bound inference work, not an exact
 * monetary price, and no retries add hidden calls.
 *
 * Cache checks require prefix caching enabled: repeated identical input with the
 * same session must report a positive cached subset on the second request. The SDK
 * hides cached_input_tokens, so usage is checked on its raw HTTP response.
 * Grouped/separate probabilities, confidence and expected scores must agree within
 * absolute 0.02; this measures invariance, not classification accuracy.
 */
import { isIP } from "node:net";

import {
  choice,
  noul,
  score,
  TypeSafeClient,
  type Fetch,
  type Questions,
  type SystemOneResult,
} from "@typesafe-ai/sdk";
import { beforeAll, describe, expect, it } from "vitest";

const MODEL = process.env.KEV_GATEWAY_MODEL ?? "jaredpalmer/kev-9b";
const ORIGIN = process.env.KEV_GATEWAY_BASE_URL;
const WRONG_KEY = "intentionally-invalid-local-test-key";

const STATE = {
  ticket: {
    message: "I was charged twice. Please fix this today.",
    tags: ["billing", "urgent"],
    resolved: false,
  },
};

const questions = () =>
  ({
    category: choice(
      { task: "Choose the department", context: ["support"] },
      { billing: { description: "Charges or payments" }, other: null },
    ),
    billing: noul("Is the ticket about billing?", {
      true: ["Payment problem"],
      false: "Unrelated to payments",
    }),
    urgency: score(
      ["Rate urgency", { consider: "Requested deadline" }],
      [{ level: "Can wait" }, ["Needs attention today"]],
    ),
  }) satisfies Questions;

/** Reject remote hosts, DNS names, credentials and path/query surprises. */
export const localOrigin = (value: string): string => {
  const invalid = new Error(
    "KEV_GATEWAY_BASE_URL must be an HTTP loopback IP origin with a port",
  );
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw invalid;
  }
  const host = parsed.hostname.replace(/^\[|\]$/g, "");
  const loopback =
    isIP(host) !== 0 && (host === "::1" || host.startsWith("127."));
  if (
    parsed.protocol !== "http:" ||
    !loopback ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    !["", "/"].includes(parsed.pathname) ||
    parsed.search !== "" ||
    parsed.hash !== "" ||
    parsed.port === ""
  ) {
    throw invalid;
  }
  return value.replace(/\/$/, "");
};

class BudgetError extends Error {}

type Extra = Record<string, unknown>;

/**
 * Wraps the SDK transport to hold the session inside a hard budget, and to carry
 * the gateway-owned fields (`session_id`, `service_tier`) that the SDK request type
 * does not model.
 */
class Gateway {
  attempts = 0;
  inputTokens = 0;
  deadline = Date.now() + 180_000;
  #extra: Extra = {};

  constructor(
    readonly model: string,
    readonly origin: string,
    private readonly key: string,
    private readonly transport: Fetch = globalThis.fetch,
  ) {}

  guard(body: string): void {
    if (
      this.attempts >= 20 ||
      Date.now() >= this.deadline ||
      Buffer.byteLength(body) > 16_384 ||
      this.inputTokens >= 100_000
    ) {
      throw new BudgetError("Local integration budget exhausted");
    }
    this.attempts += 1;
  }

  /** The SDK consumes the response body while parsing, so keep the raw text here. */
  #lastBody = "";

  readonly fetch: Fetch = async (input, init) => {
    const body = typeof init?.body === "string" ? init.body : "";
    this.guard(body);
    const merged =
      Object.keys(this.#extra).length > 0
        ? JSON.stringify({ ...JSON.parse(body), ...this.#extra })
        : body;
    const response = await this.transport(input, { ...init, body: merged });
    this.#lastBody = await response.text();
    return new globalThis.Response(this.#lastBody, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    });
  };

  client(): TypeSafeClient {
    return new TypeSafeClient({
      apiKey: this.key,
      baseURL: this.origin,
      defaultModel: this.model,
      retry: { maxRetries: 0 },
      timeout: 10_000,
      fetch: this.fetch,
    });
  }

  async infer<Q extends Questions>(
    state: unknown,
    selected: Q,
    extra: Extra = {},
  ): Promise<{ result: SystemOneResult<Q>; usage: Record<string, number> }> {
    this.#extra = extra;
    let data: SystemOneResult<Q>;
    try {
      data = await this.client().systemOne({
        state: state as never,
        questions: selected,
      });
    } catch (error) {
      if (error instanceof BudgetError) throw error;
      // SDK errors can contain request/response details; never echo them or credentials.
      throw new Error("Local SDK inference failed (details suppressed)");
    } finally {
      this.#extra = {};
    }
    expect(data.model).toBe(this.model);
    expect(Object.keys(data.answers).sort()).toEqual(
      Object.keys(selected).sort(),
    );
    const raw = JSON.parse(this.#lastBody) as {
      usage: Record<string, number>;
      latency_ms?: number;
    };
    const usage = raw.usage;
    for (const name of [
      "input_tokens",
      "cached_input_tokens",
      "output_tokens",
    ]) {
      expect(Number.isInteger(usage[name])).toBe(true);
    }
    expect(usage.input_tokens!).toBeGreaterThan(0);
    expect(usage.cached_input_tokens!).toBeGreaterThanOrEqual(0);
    expect(usage.cached_input_tokens!).toBeLessThanOrEqual(usage.input_tokens!);
    expect(usage.output_tokens).toBe(0);
    this.inputTokens += usage.input_tokens!;
    expect(this.inputTokens, "Input token budget exceeded").toBeLessThanOrEqual(
      100_000,
    );
    if (raw.latency_ms !== undefined) {
      expect(Number.isFinite(raw.latency_ms) && raw.latency_ms >= 0).toBe(true);
    }
    return { result: data, usage };
  }

  async post(payload: unknown, wrongKey = false): Promise<Response> {
    const body = JSON.stringify(payload);
    try {
      return await this.fetch(`${this.origin}/v1/systemone`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${wrongKey ? WRONG_KEY : this.key}`,
        },
        body,
      });
    } catch (error) {
      if (error instanceof BudgetError) throw error;
      throw new Error("Local HTTP check failed (details suppressed)");
    }
  }
}

const probability = (value: number): void => {
  expect(Number.isFinite(value)).toBe(true);
  expect(value).toBeGreaterThanOrEqual(0);
  expect(value).toBeLessThanOrEqual(1);
};

const sum = (values: Iterable<number>): number =>
  [...values].reduce((a, b) => a + b, 0);

describe.skipIf(!ORIGIN)("isolated local gateway", () => {
  let gateway: Gateway;

  beforeAll(() => {
    const key = process.env.KEV_GATEWAY_API_KEY;
    if (!key)
      throw new Error("Set KEV_GATEWAY_API_KEY and exact KEV_GATEWAY_MODEL");
    gateway = new Gateway(MODEL, localOrigin(ORIGIN!), key);
  });

  it("answers choice, noul and score questions", async () => {
    const { result } = await gateway.infer(STATE, questions(), {
      service_tier: "default",
    });
    const category = result.answers.category;
    expect(["billing", "other"]).toContain(category.choice);
    expect(Object.keys(category.probabilities).sort()).toEqual([
      "billing",
      "other",
    ]);
    for (const value of Object.values(category.probabilities))
      probability(value);
    expect(sum(Object.values(category.probabilities))).toBeCloseTo(1, 1);
    probability(category.confidence);
    probability(result.answers.billing.noul);
    const urgency = result.answers.urgency;
    expect(Object.keys(urgency.probabilities).sort()).toEqual(["0", "1"]);
    expect(Object.keys(urgency.legend).sort()).toEqual(["0", "1"]);
    expect(urgency.score).toBeGreaterThanOrEqual(0);
    expect(urgency.score).toBeLessThanOrEqual(1);
    probability(urgency.confidence);
    for (const value of Object.values(urgency.probabilities))
      probability(value);
    expect(sum(Object.values(urgency.probabilities))).toBeCloseTo(1, 1);
    expect(urgency.score).toBeCloseTo(
      (urgency.probabilities as Record<string, number>)["1"]!,
      1,
    );
  });

  it.each([
    { label: "text", state: "Charged twice." },
    { label: "array", state: [STATE, { history: [null, 1, true] }] },
  ])("accepts $label state", async ({ state }) => {
    const { result } = await gateway.infer(state, {
      billing: questions().billing,
    });
    probability(result.answers.billing.noul);
  });

  it("is invariant between grouped and separate questions", async () => {
    const selected = questions();
    const { result: grouped } = await gateway.infer(STATE, selected);
    for (const [name, question] of Object.entries(selected)) {
      const { result: separate } = await gateway.infer(STATE, {
        [name]: question,
      });
      const left = grouped.answers[name as keyof typeof selected] as any;
      const right = (separate.answers as any)[name];
      expect(left.type).toBe(right.type);
      if (left.type === "noul") {
        expect(left.noul).toBeCloseTo(right.noul, 1);
      } else {
        for (const key of Object.keys(left.probabilities)) {
          expect(left.probabilities[key]).toBeCloseTo(
            right.probabilities[key],
            1,
          );
        }
        expect(left.confidence).toBeCloseTo(right.confidence, 1);
        if (left.type === "score") {
          expect(left.legend).toEqual(right.legend);
          expect(left.score).toBeCloseTo(right.score, 1);
        }
        // Tied or near-tied probabilities may legitimately change the choice label.
      }
    }
  });

  it.each([
    { kind: "choice", criteria: {} },
    {
      kind: "choice",
      criteria: Object.fromEntries(
        [...Array(256).keys()].map((i) => [String(i), null]),
      ),
    },
    { kind: "score", criteria: [] },
    { kind: "score", criteria: ["only"] },
    { kind: "score", criteria: Array(256).fill(null) },
  ])("rejects out-of-range $kind criteria", async ({ kind, criteria }) => {
    const response = await gateway.post({
      model: gateway.model,
      state: "x",
      questions: { q: { type: kind, instructions: "Choose", criteria } },
    });
    expect([400, 422]).toContain(response.status);
  });

  it("rejects a wrong key", async () => {
    const response = await gateway.post(
      {
        model: gateway.model,
        state: "x",
        questions: { q: { type: "noul", instructions: "Is x present?" } },
      },
      true,
    );
    expect(response.status).toBe(401);
  });

  it("reports usage and a warm prefix cache", async () => {
    const selected = { billing: questions().billing };
    const probe = crypto.randomUUID().replaceAll("-", "");
    // Approximately 650 tokens: comfortably above the runtime's 384-token cache
    // eligibility threshold, still below the request/body/token test budgets.
    const state = {
      probe,
      ticket:
        "This synthetic billing ticket reports a duplicate payment. ".repeat(
          64,
        ),
    };
    const session = `kev-sdk-cache-${probe}`;
    const { usage: first } = await gateway.infer(state, selected, {
      session_id: session,
    });
    const { usage: second } = await gateway.infer(state, selected, {
      session_id: session,
    });
    expect(first.input_tokens).toBe(second.input_tokens);
    expect(second.cached_input_tokens!).toBeGreaterThan(0);
    expect(second.cached_input_tokens!).toBeGreaterThanOrEqual(
      first.cached_input_tokens!,
    );
  });
});

describe("harness", () => {
  it.each([
    "https://api.typesafe.ai",
    "http://example.com:3002",
    "http://localhost:3002",
    "http://127.0.0.1:3002/v1",
    "http://user:password@127.0.0.1:3002",
    "http://127.0.0.1:3002?key=secret",
    "http://127.0.0.1",
  ])("rejects the non-local or ambiguous origin %s", (origin) => {
    expect(() => localOrigin(origin)).toThrow(/loopback/);
  });

  // Synthetic transport check only; does not claim gateway or model verification.
  it("holds the SDK wire contract", async () => {
    const seen: any[] = [];
    const transport: Fetch = async (_input, init) => {
      const body = JSON.parse(init!.body as string);
      seen.push(body);
      const headers = init!.headers as Record<string, string>;
      const authorization = headers.Authorization ?? headers.authorization;
      if (authorization === `Bearer ${WRONG_KEY}`) {
        return new globalThis.Response(
          JSON.stringify({ error: { message: "Invalid key" } }),
          {
            status: 401,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      return new globalThis.Response(
        JSON.stringify({
          model: "isolated/model",
          answers: {
            category: {
              type: "choice",
              choice: "billing",
              confidence: 0.8,
              probabilities: { billing: 0.9, other: 0.1 },
            },
            billing: { type: "noul", noul: 0.9 },
            urgency: {
              type: "score",
              score: 0.8,
              confidence: 0.8,
              legend: { 0: "Can wait", 1: "Today" },
              probabilities: { 0: 0.2, 1: 0.8 },
            },
          },
          usage: {
            input_tokens: 20,
            cached_input_tokens: 10,
            output_tokens: 0,
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };
    const target = new Gateway(
      "isolated/model",
      "http://127.0.0.1:1",
      "synthetic-local-only",
      transport,
    );
    const { result, usage } = await target.infer(STATE, questions(), {
      session_id: "synthetic",
    });
    expect(result.answers.category.choice).toBe("billing");
    expect(result.answers.billing.noul).toBe(0.9);
    expect(result.answers.urgency.probabilities).toEqual({ 0: 0.2, 1: 0.8 });
    expect(usage.cached_input_tokens).toBe(10);
    expect((await target.post(seen[0], true)).status).toBe(401);
    expect(target.attempts).toBe(2);
    expect(seen).toHaveLength(2);
    expect(seen[0].model).toBe("isolated/model");
    expect(seen[0].state).toEqual(STATE);
    expect(seen[0].session_id).toBe("synthetic");
    expect(seen[0].questions.category.instructions).toEqual({
      task: "Choose the department",
      context: ["support"],
    });
  });

  it.each(["requests", "tokens", "time", "body"])(
    "enforces the %s budget",
    (budget) => {
      const target = new Gateway(
        "isolated/model",
        "http://127.0.0.1:1",
        "synthetic-local-only",
      );
      if (budget === "requests") target.attempts = 20;
      if (budget === "tokens") target.inputTokens = 100_000;
      if (budget === "time") target.deadline = Date.now() - 1;
      const body = "x".repeat(budget === "body" ? 16_385 : 1);
      expect(() => target.guard(body)).toThrow(/budget exhausted/);
    },
  );
});
