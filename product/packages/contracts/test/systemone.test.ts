import { describe, expect, it } from "vitest";

import {
  SYSTEMONE_MAX_QUESTIONS,
  SystemOneRequestSchema,
  SystemOneResponseSchema,
} from "../src/index.js";

const question = {
  type: "choice",
  instructions: "Pick",
  criteria: { yes: null },
};
const request = {
  model: "jared/kev-9b",
  state: "Hello",
  questions: { topic: question },
};
const options = (count: number) =>
  Object.fromEntries(
    Array.from({ length: count }, (_, i) => [`option-${i}`, null]),
  );
const withQuestion = (value: unknown) => ({
  ...request,
  questions: { topic: value },
});

describe("native SystemOne request contract", () => {
  it.each(["text", {}, [], { nested: [null, true, 1, { text: "hi" }] }])(
    "accepts text or structured state: %j",
    (state) => {
      expect(
        SystemOneRequestSchema.parse({ ...request, state }).service_tier,
      ).toBe("default");
    },
  );

  it.each([
    question,
    { ...question, criteria: options(255) },
    { type: "noul", instructions: { task: ["Check", { threshold: 1 }] } },
    { type: "noul", instructions: null, criteria: null },
    {
      type: "noul",
      instructions: false,
      criteria: { true: ["yes"], false: { no: null } },
    },
    {
      type: "score",
      instructions: 42,
      criteria: [null, { level: ["high", true] }],
    },
    { type: "score", instructions: [], criteria: Array(255).fill("level") },
  ])("accepts upstream JSON questions: %j", (value) => {
    expect(SystemOneRequestSchema.safeParse(withQuestion(value)).success).toBe(
      true,
    );
  });

  it("accepts envelope boundaries without changing the exact model", () => {
    const value = {
      ...request,
      model: "X".repeat(200),
      session_id: "s".repeat(256),
      questions: Object.fromEntries(
        Array.from({ length: SYSTEMONE_MAX_QUESTIONS }, (_, i) => [
          String(i).padStart(200, "q"),
          question,
        ]),
      ),
    };

    expect(SystemOneRequestSchema.parse(value)).toEqual({
      ...value,
      service_tier: "default",
    });
  });

  it("accepts more than 64 questions", () => {
    const questions = Object.fromEntries(
      Array.from({ length: 65 }, (_, i) => [String(i), question]),
    );

    expect(
      SystemOneRequestSchema.safeParse({ ...request, questions }).success,
    ).toBe(true);
  });

  it("keeps list choice criteria as sent, in order (the gateway rewrites them)", () => {
    const parsed = SystemOneRequestSchema.parse(
      withQuestion({ type: "choice", criteria: ["10", "2", "billing"] }),
    );

    expect(parsed.questions.topic).toEqual({
      type: "choice",
      criteria: ["10", "2", "billing"],
    });
  });

  it.each([
    [["only"]],
    [Array.from({ length: 255 }, (_, i) => `option-${i}`)],
    [["😀", " ", "a".repeat(10_000)]],
  ])("accepts list choice criteria: case %#", (labels) => {
    expect(
      SystemOneRequestSchema.safeParse(
        withQuestion({ ...question, criteria: labels }),
      ).success,
    ).toBe(true);
  });

  it.each([
    [[]],
    [Array.from({ length: 256 }, (_, i) => `option-${i}`)],
    [["a", "a"]],
    [["a", "b", "a"]],
    [[""]],
    [["a", ""]],
    [["a", null]],
    [["a", 1]],
    [["a", ["b"]]],
    [["a", { b: null }]],
    [[true]],
  ])("rejects invalid list choice criteria: %j", (labels) => {
    expect(
      SystemOneRequestSchema.safeParse(
        withQuestion({ ...question, criteria: labels }),
      ).success,
    ).toBe(false);
  });

  it("validates recursive JSON shape independently of runtime depth limits", () => {
    let nested: unknown = null;

    for (let i = 0; i < 40; i++) {
      nested = { nested: [nested] };
    }

    expect(
      SystemOneRequestSchema.safeParse(
        withQuestion({ ...question, instructions: nested }),
      ).success,
    ).toBe(true);
  });

  it.each([
    { model: undefined },
    { model: "" },
    { model: "x".repeat(201) },
    { state: undefined },
    { state: null },
    { state: 1 },
    { state: true },
    { state: { invalid: undefined } },
    { state: [Infinity] },
    { questions: {} },
    { questions: options(65) },
    {
      questions: Object.fromEntries(
        Array.from({ length: SYSTEMONE_MAX_QUESTIONS + 1 }, (_, i) => [
          String(i),
          question,
        ]),
      ),
    },
    { questions: { "": question } },
    { questions: { ["q".repeat(201)]: question } },
    { session_id: "" },
    { session_id: "s".repeat(257) },
    { session_id: null },
    { service_tier: "fast" },
    { service_tier: "flex" },
    { service_tier: null },
    { stream: false },
    { stream: true },
    { max_tokens: 1 },
    { max_completion_tokens: 1 },
    { max_output_tokens: 1 },
    { temperature: 0 },
    { unknown: true },
  ])("rejects invalid envelope: %j", (patch) => {
    expect(
      SystemOneRequestSchema.safeParse({ ...request, ...patch }).success,
    ).toBe(false);
  });

  it.each([
    { ...question, instructions: undefined },
    { type: "noul" },
    { type: "noul", criteria: { true: "Angry", false: "Calm" } },
    { type: "score", criteria: ["calm", "annoyed", "furious"] },
    { type: "score", instructions: "Rank", criteria: ["only"] },
  ])(
    "accepts what TypeSafe's API accepts (optional instructions, one-level scores): %j",
    (value) => {
      expect(
        SystemOneRequestSchema.safeParse(withQuestion(value)).success,
      ).toBe(true);
    },
  );

  it.each([
    { ...question, instructions: NaN },
    { ...question, instructions: { x: () => 1 } },
    { ...question, type: "unknown" },
    { ...question, extra: true },
    { ...question, criteria: {} },
    { ...question, criteria: options(256) },
    { ...question, criteria: [] },
    { ...question, criteria: null },
    { type: "score", instructions: "Rank", criteria: [] },
    { type: "score", instructions: "Rank", criteria: Array(256).fill(null) },
    { type: "score", instructions: "Rank", criteria: { a: null, b: null } },
    { type: "noul", instructions: "Check", criteria: [] },
    {
      type: "noul",
      instructions: "Check",
      criteria: { yes: "Not a supported key" },
    },
    { type: "noul", instructions: "Check", criteria: options(256) },
  ])("rejects invalid question: %j", (value) => {
    expect(SystemOneRequestSchema.safeParse(withQuestion(value)).success).toBe(
      false,
    );
  });
});

const response = {
  model: request.model,
  answers: {
    topic: {
      type: "choice",
      choice: "yes",
      confidence: 1,
      probabilities: { yes: 1 },
    },
    billing: { type: "noul", noul: 0.8 },
    urgency: {
      type: "score",
      score: 0.75,
      confidence: 0.75,
      legend: { "0": "low", "1": "high" },
      probabilities: { "0": 0.25, "1": 0.75 },
    },
  },
  usage: { input_tokens: 20, cached_input_tokens: 10, output_tokens: 0 },
};

describe("native SystemOne response contract", () => {
  it("accepts all native answer kinds and optional latency", () => {
    expect(SystemOneResponseSchema.parse(response)).toEqual(response);
    expect(
      SystemOneResponseSchema.parse({ ...response, latency_ms: 1.5 })
        .latency_ms,
    ).toBe(1.5);
  });

  it("accepts independently rounded probabilities", () => {
    expect(
      SystemOneResponseSchema.safeParse({
        ...response,
        answers: {
          q: {
            type: "choice",
            choice: "a",
            confidence: 0,
            probabilities: { a: 0.33, b: 0.33, c: 0.33 },
          },
        },
      }).success,
    ).toBe(true);
  });

  it.each([
    { output_tokens: 1 },
    { cached_input_tokens: 21 },
    { input_tokens: -1 },
    { input_tokens: 1.5 },
    { cached_input_tokens: -1 },
    { cached_input_tokens: undefined },
    { output_tokens: undefined },
    { output_tokens: "0" },
  ])("rejects invalid usage: %j", (patch) => {
    expect(
      SystemOneResponseSchema.safeParse({
        ...response,
        usage: { ...response.usage, ...patch },
      }).success,
    ).toBe(false);
  });

  it.each([
    { answers: {} },
    { latency_ms: -1 },
    { latency_ms: Infinity },
    { extra: true },
    { answers: { q: { type: "noul", noul: 1.01 } } },
    { answers: { q: { type: "noul", noul: -0.01 } } },
    { answers: { q: { ...response.answers.topic, confidence: 2 } } },
    {
      answers: {
        q: { ...response.answers.topic, probabilities: { yes: NaN } },
      },
    },
    { answers: { q: { ...response.answers.urgency, score: 255 } } },
    {
      answers: {
        q: { ...response.answers.urgency, legend: { "-1": "bad", "0": "low" } },
      },
    },
  ])("rejects invalid response: %j", (patch) => {
    expect(
      SystemOneResponseSchema.safeParse({ ...response, ...patch }).success,
    ).toBe(false);
  });
});
