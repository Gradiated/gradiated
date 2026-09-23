import {
  choice,
  noul,
  score,
  TypeSafeClient,
  type Fetch,
} from "@typesafe-ai/sdk";
import { expect, it } from "vitest";

import {
  SystemOneRequestSchema,
  SystemOneResponseSchema,
  type SystemOneResponse,
} from "../packages/contracts/src/systemone.js";

const MODEL = "isolated/model";

const STATE = {
  ticket: {
    message: "I was charged twice. Please fix this today.",
    tags: ["billing", "urgent"],
    resolved: false,
  },
};

const DECISION: SystemOneResponse = SystemOneResponseSchema.parse({
  model: MODEL,
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
  usage: { input_tokens: 20, cached_input_tokens: 10, output_tokens: 0 },
});

interface SentRequest {
  url: string;
  authorization: string | null;
  body: unknown;
}

it("sends and reads the SystemOne wire shapes the gateway serves", async () => {
  const sent: SentRequest[] = [];
  const transport: Fetch = async (input, init) => {
    if (typeof init?.body !== "string") {
      throw new Error("SDK sent a non-string body");
    }

    sent.push({
      url: String(input),
      authorization: new Headers(init.headers).get("authorization"),
      body: JSON.parse(init.body),
    });

    return Response.json(DECISION);
  };
  const client = new TypeSafeClient({
    apiKey: "synthetic-local-only",
    baseURL: "http://127.0.0.1:1",
    defaultModel: MODEL,
    retry: { maxRetries: 0 },
    fetch: transport,
  });

  const request = {
    state: STATE,
    session_id: "synthetic",
    questions: {
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
    },
  };

  const result = await client.systemOne(request);

  expect(sent).toEqual([
    {
      url: "http://127.0.0.1:1/v1/systemone",
      authorization: "Bearer synthetic-local-only",
      body: expect.anything(),
    },
  ]);
  expect(SystemOneRequestSchema.parse(sent[0]?.body)).toMatchObject({
    model: MODEL,
    state: STATE,
    session_id: "synthetic",
  });
  expect(result.model).toBe(MODEL);
  expect(result.answers.category.choice).toBe("billing");
  expect(result.answers.billing.noul).toBe(0.9);
  expect(result.answers.urgency.score).toBe(0.8);
  expect(result.answers.urgency.probabilities).toEqual({ 0: 0.2, 1: 0.8 });
});
