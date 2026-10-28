import {
  catalogModel,
  TRAINING_ONLY_MODELS,
} from "@gradiated/contracts/model-catalog";

import type {
  ChatCompletionParameters,
  ChatCompletionUsage,
} from "@/api/inference";
import type { Model } from "@/api/queries";
import type { components } from "@/api/schema";
import { formatLatency, formatUsd } from "@/lib/format";
import type { TaskRow } from "@/store/fine-tuning-types";

const API_BASE_URL = "https://api.gradiated.com";

export type ServiceTier = components["schemas"]["ServiceTier"];
export type ParameterDescriptor =
  components["schemas"]["ModelParameterDescriptor"];
export type ModelParameters = Readonly<Record<string, ParameterDescriptor>>;
type DefaultParameters = NonNullable<Model["properties"]["default_parameters"]>;
type ModelReasoning = NonNullable<Model["properties"]["reasoning"]>;

// What the catalog says a model accepts; the gateway drops any other parameter.
export interface ModelCapabilities {
  parameters: ModelParameters;
  outputTokens: OutputTokens | undefined;
  defaults: DefaultParameters;
  reasoning: ModelReasoning | undefined;
}

export const NO_CAPABILITIES: ModelCapabilities = {
  parameters: {},
  outputTokens: undefined,
  defaults: {},
  reasoning: undefined,
};

export interface PlaygroundSettings {
  model: string;
  capabilities: ModelCapabilities;
  systemPrompt: string;
  serviceTier: ServiceTier;
  reasoningEffort: string | undefined;
  temperature: number | undefined;
  maxTokens: number | undefined;
  topP: number | undefined;
  seed: number | undefined;
  frequencyPenalty: number | undefined;
  presencePenalty: number | undefined;
  stop: string;
  jsonOutput: boolean;
}

export type PlaygroundSettingsPatch = Partial<
  Omit<PlaygroundSettings, "capabilities">
>;

export interface OutputTokens {
  default: number;
  max: number;
}

export interface ResponseStats {
  firstTokenMs: number | undefined;
  totalMs: number;
  usage: ChatCompletionUsage | undefined;
}

export type PlaygroundMessage =
  | { id: string; role: "user"; content: string }
  | {
      id: string;
      role: "assistant";
      content: string;
      reasoning: string;
      status: "streaming" | "complete" | "stopped" | "failed";
      error?: string;
      stats?: ResponseStats;
    };

export type AssistantMessage = Extract<
  PlaygroundMessage,
  { role: "assistant" }
>;

export type ModelSource = "hosted" | "workspace";

export interface PlaygroundModel {
  id: string;
  label: string;
  iconId: string;
  source: ModelSource;
  available: boolean;
  capabilities: ModelCapabilities;
}

export const MODEL_SOURCE_LABEL: Record<ModelSource, string> = {
  hosted: "Hosted models",
  workspace: "Your models",
};

// Unset values take the model's catalog default, which the panel shows and requests send.
export type PlaygroundOptions = Omit<
  PlaygroundSettings,
  "model" | "capabilities"
>;

export const DEFAULT_SETTINGS: PlaygroundOptions = {
  systemPrompt: "",
  serviceTier: "default",
  reasoningEffort: undefined,
  temperature: undefined,
  maxTokens: undefined,
  topP: undefined,
  seed: undefined,
  frequencyPenalty: undefined,
  presencePenalty: undefined,
  stop: "",
  jsonOutput: false,
};

export const reasoningEfforts = ({
  parameters,
  reasoning,
}: ModelCapabilities): string[] => {
  if (!supports(parameters, "reasoning_effort")) return [];

  const descriptor = parameters.reasoning_effort;

  return (
    reasoning?.supported_efforts ??
    (descriptor?.type === "enum" ? descriptor.values.map(String) : [])
  );
};

export interface EffectiveSettings {
  temperature: number | undefined;
  topP: number | undefined;
  frequencyPenalty: number | undefined;
  presencePenalty: number | undefined;
  maxTokens: number | undefined;
  reasoningEffort: string | undefined;
}

// A value the catalog does not publish stays unset and is not sent.
export const effectiveSettings = (
  settings: PlaygroundSettings,
): EffectiveSettings => {
  const { defaults, outputTokens, reasoning } = settings.capabilities;
  const efforts = reasoningEfforts(settings.capabilities);
  const effort = settings.reasoningEffort;

  return {
    temperature: settings.temperature ?? defaults.temperature ?? undefined,
    topP: settings.topP ?? defaults.top_p ?? undefined,
    frequencyPenalty:
      settings.frequencyPenalty ?? defaults.frequency_penalty ?? undefined,
    presencePenalty:
      settings.presencePenalty ?? defaults.presence_penalty ?? undefined,
    maxTokens: settings.maxTokens ?? outputTokens?.default,
    reasoningEffort:
      effort !== undefined && efforts.includes(effort)
        ? effort
        : (reasoning?.default_effort ?? undefined),
  };
};

export const supports = (parameters: ModelParameters, name: string) =>
  Object.hasOwn(parameters, name);

const capabilities = (model: Model | undefined): ModelCapabilities => {
  const output = model?.properties.output_modalities.find(
    ({ type }) => type === "text",
  );

  return {
    parameters: output?.supported_parameters ?? {},
    outputTokens: output && {
      default: output.default_length.value,
      max: output.max_length.value,
    },
    defaults: model?.properties.default_parameters ?? {},
    reasoning: model?.properties.reasoning,
  };
};

// A task is callable by its name once it has a production version.
export const playgroundModels = (
  hosted: readonly Model[],
  tasks: readonly TaskRow[],
): PlaygroundModel[] => [
  ...hosted
    .filter(
      (model) =>
        model.properties.type === "chat" &&
        !TRAINING_ONLY_MODELS.some((base) => base.id === model.id),
    )
    .map((model) => ({
      id: model.id,
      label: catalogModel(model.id)?.displayName ?? model.name,
      iconId: model.id,
      source: "hosted" as const,
      available: model.status === "available",
      capabilities: capabilities(model),
    })),
  // The gateway rejects a task name that is also a hosted model id as ambiguous.
  ...tasks
    .filter(
      (task) =>
        task.production_version_id !== null &&
        !hosted.some((model) => model.id === task.name),
    )
    .map((task) => ({
      id: task.name,
      label: task.name,
      iconId: task.base_model_id ?? task.name,
      source: "workspace" as const,
      available: true,
      capabilities: capabilities(
        hosted.find((model) => model.id === task.base_model_id),
      ),
    })),
];

export type PlaygroundRequest = Omit<ChatCompletionParameters, "session_id">;

export const chatRequest = (
  settings: PlaygroundSettings,
  messages: readonly PlaygroundMessage[],
): PlaygroundRequest => {
  const system = settings.systemPrompt.trim();
  const history: PlaygroundRequest["messages"] = messages
    .filter(
      (message) =>
        message.role === "user" ||
        (message.status !== "failed" && message.content !== ""),
    )
    .map(({ role, content }) => ({ role, content }));
  const effective = effectiveSettings(settings);

  return {
    model: settings.model,
    messages: system
      ? [{ role: "system", content: system }, ...history]
      : history,
    service_tier: settings.serviceTier,
    ...optional(settings, "reasoning_effort", effective.reasoningEffort),
    ...optional(settings, "temperature", effective.temperature),
    ...optional(settings, "top_p", effective.topP),
    ...(effective.maxTokens === undefined
      ? {}
      : { max_completion_tokens: effective.maxTokens }),
    ...optional(settings, "seed", settings.seed),
    ...optional(settings, "frequency_penalty", effective.frequencyPenalty),
    ...optional(settings, "presence_penalty", effective.presencePenalty),
    ...optional(settings, "stop", stopSequences(settings.stop)),
    ...optional(
      settings,
      "response_format",
      settings.jsonOutput ? { type: "json_object" } : undefined,
    ),
  };
};

const optional = <Name extends keyof PlaygroundRequest>(
  settings: PlaygroundSettings,
  name: Name,
  value: PlaygroundRequest[Name] | undefined,
): Partial<PlaygroundRequest> =>
  value !== undefined && supports(settings.capabilities.parameters, name)
    ? { [name]: value }
    : {};

// One stop sequence per line; blank lines are ignored.
const stopSequences = (text: string): string[] | undefined => {
  const sequences = text.split("\n").filter((line) => line !== "");

  return sequences.length ? sequences : undefined;
};

export const replyStats = ({
  firstTokenMs,
  totalMs,
  usage,
}: ResponseStats): string[] => {
  const tokens = usage?.completion_tokens;
  const generatingMs = totalMs - (firstTokenMs ?? 0);

  return [
    ...(tokens === undefined ? [] : [`${tokens} tokens`]),
    ...(tokens && generatingMs > 0
      ? [`${Math.round((tokens * 1000) / generatingMs)} tok/s`]
      : []),
    ...(firstTokenMs === undefined
      ? []
      : [`${formatLatency(firstTokenMs)} to first token`]),
    ...(usage ? [formatUsd(usage.cost)] : []),
  ];
};

export type CodeLanguage = "curl" | "python" | "typescript";

export const CODE_LANGUAGES: { value: CodeLanguage; label: string }[] = [
  { value: "curl", label: "cURL" },
  { value: "python", label: "Python" },
  { value: "typescript", label: "TypeScript" },
];

const indent = (text: string, spaces: number) =>
  text.replaceAll("\n", `\n${" ".repeat(spaces)}`);

export const requestSnippet = (
  language: CodeLanguage,
  request: PlaygroundRequest,
): string => {
  const { model, messages, ...options } = request;

  switch (language) {
    case "curl":
      return `curl ${API_BASE_URL}/v1/chat/completions \\
  -H "Authorization: Bearer $GRADIATED_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '${JSON.stringify(request, null, 2).replaceAll("'", "'\\''")}'`;
    case "python":
      return `import os
from openai import OpenAI

client = OpenAI(
    base_url="${API_BASE_URL}/v1",
    api_key=os.environ["GRADIATED_API_KEY"],
)

completion = client.chat.completions.create(
    model=${JSON.stringify(model)},
    messages=${indent(JSON.stringify(messages, null, 4), 4)},
${Object.entries(options)
  .map(([key, value]) => `    ${key}=${JSON.stringify(value)},\n`)
  .join("")})

print(completion.choices[0].message.content)`;
    case "typescript":
      return `import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "${API_BASE_URL}/v1",
  apiKey: process.env.GRADIATED_API_KEY,
});

const completion = await client.chat.completions.create(${JSON.stringify(request, null, 2)});

console.log(completion.choices[0].message.content);`;
  }
};
