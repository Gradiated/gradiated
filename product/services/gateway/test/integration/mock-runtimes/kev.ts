// Synthetic native SystemOne profile; mirrors wire semantics, not model behaviour.
import {
  isJsonObject,
  text,
  type JsonObject,
  type JsonValue,
} from "../json.js";
import type { RuntimeProfile } from "./profile.js";

const PATH = "/v1/systemone";

const REQUEST_FIELDS = ["model", "state", "questions", "priority"];
const QUESTION_TYPES = ["noul", "choice", "score"] as const;
const MAX_QUESTIONS = 64;

type QuestionType = (typeof QUESTION_TYPES)[number];

interface Question {
  readonly name: string;
  readonly type: QuestionType;
  readonly criteria: JsonValue | undefined;
}

const isQuestionType = (value: JsonValue | undefined): value is QuestionType =>
  QUESTION_TYPES.some((type) => type === value);

const questions = (body: JsonObject): Question[] => {
  if (!isJsonObject(body.questions)) {
    throw new Error("questions must be an object");
  }

  const entries = Object.entries(body.questions);
  if (entries.length < 1 || entries.length > MAX_QUESTIONS) {
    throw new Error("question count out of range");
  }

  return entries.map(([name, question]) => {
    if (!isJsonObject(question) || typeof question.instructions !== "string") {
      throw new Error("question missing instructions");
    }
    if (!isQuestionType(question.type)) {
      throw new Error("unknown question type");
    }

    return { name, type: question.type, criteria: question.criteria };
  });
};

const criteriaLabels = (criteria: JsonValue | undefined): string[] => {
  if (isJsonObject(criteria)) return Object.keys(criteria);

  if (!Array.isArray(criteria)) {
    throw new Error("criteria must be a list or an object");
  }

  return criteria.map((label) => text(label));
};

const answer = (question: Question): JsonObject => {
  if (question.type === "noul") return { type: "noul", noul: 0.75 };

  const labels = criteriaLabels(question.criteria);
  const keys =
    question.type === "choice"
      ? labels
      : labels.map((_, index) => String(index));
  const probabilities = Object.fromEntries(
    keys.map((key, index) => [key, index === 0 ? 1 : 0]),
  );

  if (question.type === "choice") {
    return {
      type: "choice",
      confidence: 1.0,
      probabilities,
      choice: keys[0] ?? null,
    };
  }

  return {
    type: "score",
    confidence: 1.0,
    probabilities,
    score: 0.0,
    legend: Object.fromEntries(keys.map((key, index) => [key, labels[index]!])),
  };
};

export const validate = (body: JsonObject, model: string): void => {
  const fields = Object.keys(body);
  if (
    fields.length !== REQUEST_FIELDS.length ||
    REQUEST_FIELDS.some((field) => !fields.includes(field))
  ) {
    throw new Error(`unexpected request fields: ${fields.join(",")}`);
  }
  if (body.model !== model) throw new Error("wrong private model");
  const state = body.state;
  if (
    typeof state !== "string" &&
    !isJsonObject(state) &&
    !Array.isArray(state)
  ) {
    throw new Error("state must be text or structured JSON");
  }
  if (body.priority !== 0) throw new Error("priority must be zero");

  questions(body);
};

export const response = (body: JsonObject, cached = 0): JsonObject => ({
  model: text(body.model),
  answers: Object.fromEntries(
    questions(body).map((question) => [question.name, answer(question)]),
  ),
  usage: { input_tokens: 100, cached_input_tokens: cached, output_tokens: 0 },
});

// Native decisions are prefill-only; the runtime never streams.
export const events = (): never => {
  throw new Error("the native decision protocol does not stream");
};

export const profile: RuntimeProfile = {
  path: PATH,
  validate,
  response,
  events,
};
