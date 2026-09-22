// Synthetic native SystemOne profile; mirrors wire semantics, not model behaviour.
import type { JsonObject, JsonValue, RuntimeProfile } from "./profile.js";

export const PATH = "/v1/systemone";

const QUESTION_TYPES = new Set(["noul", "choice", "score"]);

export const validate = (body: JsonObject, model: string): void => {
  const fields = new Set(Object.keys(body));
  const expected = ["model", "state", "questions", "priority"];
  if (
    fields.size !== expected.length ||
    expected.some((key) => !fields.has(key))
  ) {
    throw new Error(`unexpected request fields: ${[...fields].join(",")}`);
  }
  if (body.model !== model) throw new Error("wrong private model");
  const state = body.state;
  if (
    typeof state !== "string" &&
    (state === null || typeof state !== "object")
  ) {
    throw new Error("state must be text or structured JSON");
  }
  if (body.priority !== 0) throw new Error("priority must be zero");
  const questions = body.questions as JsonObject;
  const names = Object.keys(questions ?? {});
  if (names.length < 1 || names.length > 64)
    throw new Error("question count out of range");
  for (const name of names) {
    const question = questions[name] as JsonObject;
    if (!("instructions" in question))
      throw new Error("question missing instructions");
    if (!QUESTION_TYPES.has(question.type as string))
      throw new Error("unknown question type");
  }
};

export const response = (body: JsonObject, cached = 0): JsonObject => {
  const questions = body.questions as JsonObject;
  const answers: JsonObject = {};
  for (const [name, value] of Object.entries(questions)) {
    const question = value as JsonObject;
    const kind = question.type as string;
    if (kind === "noul") {
      answers[name] = { type: kind, noul: 0.75 };
      continue;
    }
    const criteria = question.criteria as JsonValue;
    const entries = Array.isArray(criteria)
      ? criteria
      : Object.keys(criteria as JsonObject);
    const keys =
      kind === "choice"
        ? (entries as string[])
        : entries.map((_, index) => String(index));
    const answer: JsonObject = {
      type: kind,
      confidence: 1.0,
      probabilities: Object.fromEntries(
        keys.map((key, index) => [key, index === 0 ? 1 : 0]),
      ),
    };
    if (kind === "choice") {
      answer.choice = keys[0]!;
    } else {
      answer.score = 0.0;
      answer.legend = Object.fromEntries(
        keys.map((key, index) => [key, String(entries[index])]),
      );
    }
    answers[name] = answer;
  }
  return {
    model: body.model as string,
    answers,
    usage: { input_tokens: 100, cached_input_tokens: cached, output_tokens: 0 },
  };
};

// Native decisions are prefill-only; the runtime never streams.
export const events = (): never => {
  throw new Error("the native decision protocol does not stream");
};

export const profile: RuntimeProfile = { PATH, validate, response, events };
