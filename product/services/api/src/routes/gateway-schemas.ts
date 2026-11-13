import { GenerationLogSchema, ServiceTierSchema } from "@gradiated/contracts";
import { z } from "@hono/zod-openapi";

// These describe gateway wire payloads, not Hono validation. Model capabilities
// determine accepted extensions; upstream provider features are not implied.
const wireObject = z.object({}).catchall(z.unknown());
const model = z
  .string()
  .min(1)
  .max(200)
  .describe(
    "Exact hosted model ID from GET /v1/models; no aliases or fallback.",
  );
const temperature = z
  .number()
  .optional()
  .describe(
    "Sampling randomness: lower values favor likely tokens; higher values increase variation. Supported range and default depend on the model.",
  );
const topP = z
  .number()
  .optional()
  .describe(
    "Cumulative probability cutoff for nucleus sampling. Lower values narrow the candidate tokens; support and bounds depend on the model.",
  );
const tokenLimit = z
  .number()
  .int()
  .positive()
  .optional()
  .describe(
    "Upper bound on generated tokens, subject to the selected model's output and context limits.",
  );
const common = {
  model,
  stream: z
    .boolean()
    .default(false)
    .describe(
      "When true, receive incremental server-sent events in this endpoint's protocol instead of one JSON result.",
    ),
  service_tier: ServiceTierSchema.default("default").describe(
    "Gradiated priority and price: flex uses 0.7x base pricing, default 1x, and fast 1.5x. fast has the highest scheduling priority.",
  ),
};
const contentBlock = wireObject.describe(
  "Protocol-specific content block, such as {type: 'text', text: 'Hello'}. Tool and multimodal blocks require support from the selected model and protocol translator.",
);
const message = z
  .object({
    role: z
      .string()
      .describe(
        "Speaker role, such as user or assistant; Chat Completions also supports system, developer and tool where the model accepts them.",
      ),
    content: z
      .union([z.string(), z.array(contentBlock), z.null()])
      .optional()
      .describe(
        "Message text or typed content blocks. Assistant tool-call messages may have null content.",
      ),
    name: z
      .string()
      .optional()
      .describe("Optional participant name in Chat Completions messages."),
    tool_call_id: z
      .string()
      .optional()
      .describe(
        "For a Chat Completions tool result, the ID of the assistant tool call being answered.",
      ),
    tool_calls: z
      .array(wireObject)
      .optional()
      .describe(
        "Assistant tool calls in Chat Completions format, each with an ID and function name/arguments. Supply corresponding tool results on the next request.",
      ),
  })
  .catchall(z.unknown());
const anthropicMessage = z
  .object({
    role: z
      .enum(["user", "assistant"])
      .describe(
        "Conversation speaker. Send system instructions in the top-level system field.",
      ),
    content: z
      .union([z.string(), z.array(contentBlock)])
      .describe(
        "Message text or Anthropic content blocks, including tool_use/tool_result blocks when supported.",
      ),
  })
  .catchall(z.unknown());
const openAiTools = z
  .array(wireObject)
  .optional()
  .describe(
    "Function definitions available to the model, with names, descriptions and JSON Schemas for arguments. Uses this endpoint's OpenAI wire format; provider-hosted tools are not implied.",
  );
const openAiToolChoice = z
  .union([z.string(), wireObject])
  .optional()
  .describe(
    "Tool-selection policy (none, auto or required) or a named function selection in this endpoint's format. Requires model support.",
  );

export const chatRequest = z
  .object({
    ...common,
    messages: z
      .array(message)
      .min(1)
      .describe(
        "Ordered conversation history to continue, including instructions and any previous tool results.",
      ),
    session_id: z
      .string()
      .min(1)
      .max(256)
      .optional()
      .describe(
        "Optional session affinity identifier. It is a routing hint, not stored conversation history; resend the required context.",
      ),
    max_completion_tokens: tokenLimit.describe(
      "Maximum generated tokens. Cannot be combined with max_tokens; model output and context limits still apply.",
    ),
    max_tokens: tokenLimit.describe(
      "Alternative output-token limit. Cannot be combined with max_completion_tokens.",
    ),
    temperature,
    top_p: topP,
    seed: z
      .number()
      .int()
      .optional()
      .describe(
        "Sampling seed for repeatable requests; identical output is not guaranteed.",
      ),
    frequency_penalty: z
      .number()
      .optional()
      .describe(
        "Penalty based on how often a token already appears. Positive values reduce repetition; model bounds apply.",
      ),
    presence_penalty: z
      .number()
      .optional()
      .describe(
        "Penalty for tokens already present in the output. Positive values favor new topics; model bounds apply.",
      ),
    parallel_tool_calls: z
      .boolean()
      .optional()
      .describe(
        "Allow the model to request multiple tool calls in one turn, when supported.",
      ),
    reasoning_effort: z
      .union([z.string(), z.number().int().min(1).max(100)])
      .optional()
      .describe(
        "Model-specific reasoning effort. DeepSeek also accepts integer effort from 1 to 100. Accepted values and effects depend on the hosted model.",
      ),
    chat_template_kwargs: wireObject
      .optional()
      .describe(
        "Model-specific chat-template options, such as reasoning configuration. Accepted keys depend on the runtime.",
      ),
    stop: z
      .union([z.string(), z.array(z.string())])
      .optional()
      .describe(
        "Text sequence or sequences that stop generation when encountered; supported limits depend on the model.",
      ),
    tools: openAiTools,
    tool_choice: openAiToolChoice,
    response_format: wireObject
      .optional()
      .describe(
        "Requested output format, such as text, json_object or json_schema. Structured-output support depends on the model.",
      ),
    stream_options: z
      .object({
        include_usage: z
          .boolean()
          .optional()
          .describe(
            "Request aggregate token usage in a final streaming chunk when supported. An interrupted stream may not deliver it.",
          ),
      })
      .catchall(z.unknown())
      .optional()
      .describe("Options for streaming responses; use with stream=true."),
  })
  .catchall(z.unknown())
  .openapi("ChatCompletionRequest");

export const messagesRequest = z
  .object({
    ...common,
    messages: z
      .array(anthropicMessage)
      .min(1)
      .describe(
        "Ordered user and assistant turns in Anthropic Messages format.",
      ),
    max_tokens: z
      .number()
      .int()
      .positive()
      .describe("Maximum tokens to generate; the model may finish earlier."),
    system: z
      .union([z.string(), z.array(contentBlock)])
      .optional()
      .describe(
        "Instructions that apply to the conversation, supplied separately from user and assistant turns.",
      ),
    tools: z
      .array(wireObject)
      .optional()
      .describe(
        "Callable tools in Anthropic format: name, optional description and input_schema describing arguments. The caller executes tool-use results.",
      ),
    tool_choice: wireObject
      .optional()
      .describe(
        "Anthropic tool policy: type auto, any, tool (with name), or none, subject to model and translator support.",
      ),
    temperature,
    top_p: topP,
    stop_sequences: z
      .array(z.string())
      .optional()
      .describe(
        "Custom text sequences that end generation; returned as stop_sequence when one matches.",
      ),
  })
  .catchall(z.unknown())
  .openapi("MessagesRequest");

export const responsesRequest = z
  .object({
    ...common,
    input: z
      .union([z.string(), z.array(wireObject)])
      .describe(
        "Prompt text or ordered Responses input items, including messages and function-call results. Resend context for each stateless request.",
      ),
    instructions: z
      .string()
      .optional()
      .describe(
        "System or developer instructions inserted into the model context.",
      ),
    background: z
      .literal(false)
      .nullable()
      .optional()
      .describe(
        "Use false or omit this field. Background execution is not supported.",
      ),
    max_output_tokens: tokenLimit.describe(
      "Maximum generated tokens, including reasoning tokens when produced by the model.",
    ),
    tools: openAiTools,
    tool_choice: openAiToolChoice,
    temperature,
    top_p: topP,
    store: z
      .literal(false)
      .nullable()
      .optional()
      .describe(
        "Use false or omit this field. The gateway does not store responses or accept previous_response_id, conversation or prompt references.",
      ),
  })
  .catchall(z.unknown())
  .openapi("ResponsesRequest");

const usageCost = z
  .number()
  .nonnegative()
  .describe(
    "Total charge in USD, calculated from the admission-time pricing snapshot and finalized usage. Gradiated extension to the standard usage object.",
  );

const chatUsage = z
  .object({
    cost: usageCost,
    estimated_joules: GenerationLogSchema.shape.estimated_joules.describe(
      "Estimated GPU energy used for this generation, in joules. Omitted or null when unavailable; this is an estimate, not a precise measurement.",
    ),
    prompt_tokens_details: z
      .object({
        cached_tokens: z
          .number()
          .int()
          .nonnegative()
          .describe(
            "Prompt tokens read from cache; included in prompt_tokens.",
          ),
        cache_write_tokens: z
          .number()
          .int()
          .nonnegative()
          .optional()
          .describe("Prompt tokens written to cache; omitted when zero."),
      })
      .describe("Breakdown of prompt tokens."),
    completion_tokens_details: z
      .object({
        reasoning_tokens: z
          .number()
          .int()
          .nonnegative()
          .describe("Reasoning tokens included in completion_tokens."),
      })
      .describe("Breakdown of completion tokens."),
    prompt_tokens: z
      .number()
      .int()
      .nonnegative()
      .describe("Tokens in the prompt, including any cached subset."),
    completion_tokens: z
      .number()
      .int()
      .nonnegative()
      .describe("Tokens generated by the model."),
    total_tokens: z
      .number()
      .int()
      .nonnegative()
      .describe("Sum of prompt and completion tokens."),
  })
  .catchall(z.unknown())
  .describe(
    "Token usage in Chat Completions format; model-specific cache and reasoning details may also be present.",
  );
const messagesUsage = z
  .object({
    cost: usageCost,
    cache_read_input_tokens: z
      .number()
      .int()
      .nonnegative()
      .optional()
      .describe(
        "Input tokens read from cache; excluded from input_tokens in Messages format.",
      ),
    cache_creation_input_tokens: z
      .number()
      .int()
      .nonnegative()
      .optional()
      .describe(
        "Input tokens written to cache; excluded from input_tokens in Messages format.",
      ),
    output_tokens_details: z
      .object({
        thinking_tokens: z
          .number()
          .int()
          .nonnegative()
          .describe("Internal reasoning tokens included in output_tokens."),
      })
      .optional()
      .describe("Breakdown of output tokens when reasoning usage is reported."),
    input_tokens: z
      .number()
      .int()
      .nonnegative()
      .describe("Input-token count reported in Anthropic format."),
    output_tokens: z
      .number()
      .int()
      .nonnegative()
      .describe("Output-token count reported in Anthropic format."),
  })
  .catchall(z.unknown())
  .describe(
    "Token usage translated to Anthropic format; optional cache details depend on runtime reporting.",
  );
const responsesUsage = z
  .object({
    cost: usageCost,
    input_tokens_details: z
      .object({
        cached_tokens: z
          .number()
          .int()
          .nonnegative()
          .describe("Input tokens read from cache; included in input_tokens."),
        cache_write_tokens: z
          .number()
          .int()
          .nonnegative()
          .optional()
          .describe("Input tokens written to cache; omitted when zero."),
      })
      .describe("Breakdown of input tokens."),
    output_tokens_details: z
      .object({
        reasoning_tokens: z
          .number()
          .int()
          .nonnegative()
          .describe("Reasoning tokens included in output_tokens."),
      })
      .describe("Breakdown of output tokens."),
    input_tokens: z
      .number()
      .int()
      .nonnegative()
      .describe("Tokens used for the response input."),
    output_tokens: z
      .number()
      .int()
      .nonnegative()
      .describe("Tokens generated for the response."),
    total_tokens: z
      .number()
      .int()
      .nonnegative()
      .describe("Total input and output tokens."),
  })
  .catchall(z.unknown())
  .describe(
    "Token usage translated to Responses format; model-specific details may also be present.",
  );

export const chatResponse = z
  .object({
    id: z.string().describe("Identifier for this completion."),
    object: z
      .literal("chat.completion")
      .describe("Object discriminator for a non-streaming chat completion."),
    created: z
      .number()
      .int()
      .describe("Completion creation time as Unix seconds."),
    model: model.describe("Exact model that served the completion."),
    choices: z
      .array(
        z
          .object({
            index: z
              .number()
              .int()
              .describe("Zero-based position of this completion choice."),
            message: message.describe(
              "Generated assistant message, including any tool calls.",
            ),
            finish_reason: z
              .string()
              .nullable()
              .describe(
                "Why generation ended, such as stop, length or tool_calls; null if not yet known.",
              ),
          })
          .catchall(z.unknown()),
      )
      .describe("Generated completion choices."),
    usage: chatUsage.optional(),
  })
  .catchall(z.unknown())
  .openapi("ChatCompletionResponse");

export const messagesResponse = z
  .object({
    id: z.string().describe("Identifier for the generated message."),
    type: z
      .literal("message")
      .describe("Object discriminator for an Anthropic-format message."),
    role: z
      .literal("assistant")
      .describe("The generated message is spoken by the assistant."),
    model: model.describe("Exact model that served the message."),
    content: z
      .array(contentBlock)
      .describe("Ordered output blocks, such as text and tool-use requests."),
    stop_reason: z
      .string()
      .nullable()
      .describe(
        "Why the message ended, such as end_turn, max_tokens, stop_sequence or tool_use.",
      ),
    stop_sequence: z
      .string()
      .nullable()
      .optional()
      .describe(
        "The custom stop sequence that matched, or null if none matched.",
      ),
    usage: messagesUsage,
  })
  .catchall(z.unknown())
  .openapi("MessagesResponse");

export const responsesResponse = z
  .object({
    id: z
      .string()
      .describe(
        "Identifier for the response; Gradiated does not expose stored-response retrieval.",
      ),
    object: z
      .literal("response")
      .describe("Object discriminator for a Responses result."),
    model: model.describe("Exact model that served the response."),
    status: z
      .string()
      .describe("Response lifecycle state, such as completed or incomplete."),
    output: z
      .array(wireObject)
      .describe(
        "Ordered Responses output items, such as assistant messages and function calls.",
      ),
    usage: responsesUsage.nullable().optional(),
  })
  .catchall(z.unknown())
  .openapi("ResponsesResponse");

const tokenMeasure = z.object({
  value: z.number().int().positive().describe("Number of tokens."),
  unit: z.literal("token").describe("Unit for the limit; always token."),
});
const parameterDescriptor = z.object({
  type: z
    .enum(["range", "integer", "boolean", "enum", "unknown"])
    .describe(
      "Accepted value kind. unknown means the catalog does not define a narrower shape.",
    ),
  min: z
    .number()
    .optional()
    .describe("Inclusive lower bound for range or integer parameters."),
  max: z
    .number()
    .optional()
    .describe("Inclusive upper bound for range or integer parameters."),
  unit: z
    .literal("token")
    .optional()
    .describe("Unit for a token-count parameter."),
  values: z
    .array(z.union([z.string(), z.number(), z.boolean()]))
    .optional()
    .describe("Allowed values for an enum parameter."),
});
const parameterMap = z.record(z.string(), parameterDescriptor);
const price = z.object({
  type: z
    .string()
    .describe(
      "Billable token category: prompt, cached_prompt, cache_write, completion or internal_reasoning.",
    ),
  unit: z
    .literal("token")
    .describe("Billing unit; each price applies to one token."),
  cost_usd: z
    .string()
    .describe(
      "USD price per token as a decimal string, before any service-tier multiplier.",
    ),
});
const inputModality = z.object({
  type: z.literal("text").describe("Input modality; currently text."),
  supported_inputs: z
    .object({
      max_context_length: tokenMeasure.describe(
        "Maximum combined input and output token count.",
      ),
      max_prompt_length: tokenMeasure.describe("Maximum input token count."),
    })
    .describe("Model input and context limits."),
  pricing: z
    .array(price)
    .describe(
      "Prices for prompt, cached prompt and optional cache-write tokens.",
    ),
});
const outputModality = z.object({
  type: z.literal("text").describe("Output modality; currently text."),
  max_length: tokenMeasure.describe("Maximum generated token count."),
  streaming: z
    .boolean()
    .describe("Whether the model supports incremental output."),
  supported_parameters: parameterMap.describe(
    "Inference parameters accepted by this model, with their value types and limits.",
  ),
  pricing: z
    .array(price)
    .describe("Prices for completion and optional internal-reasoning tokens."),
});

export const catalogResponse = z
  .object({
    data: z
      .array(
        z.object({
          schema_version: z
            .string()
            .describe(
              "Version of the gateway's provider model-catalog format.",
            ),
          id: model,
          name: z
            .string()
            .describe(
              "Human-readable model name; use id in inference requests.",
            ),
          created: z
            .number()
            .int()
            .describe("Model release time as Unix seconds."),
          description: z.string().describe("Human-readable model description."),
          is_ready: z
            .boolean()
            .describe(
              "Whether the model can currently accept inference requests.",
            ),
          hugging_face_id: z
            .string()
            .optional()
            .describe(
              "Upstream Hugging Face model identifier, when published.",
            ),
          tokenizer: z
            .string()
            .optional()
            .describe("Tokenizer identifier advertised for this model."),
          quantization: z
            .string()
            .optional()
            .describe(
              "Weight quantization format used by the served model, when specified.",
            ),
          deprecation_date: z
            .string()
            .optional()
            .describe("Scheduled model deprecation timestamp, when specified."),
          input_modalities: z
            .array(inputModality)
            .describe(
              "Accepted input types and input/cache pricing. Each entry has type, supported_inputs and pricing with USD costs.",
            ),
          output_modalities: z
            .array(outputModality)
            .describe(
              "Output types, token limits, streaming support, supported parameters and USD output pricing.",
            ),
          passthrough_parameters: z
            .record(z.string(), parameterDescriptor)
            .optional()
            .describe(
              "Additional model-specific parameters keyed by name, with type, bounds or allowed values.",
            ),
          datacenters: z
            .array(
              z.object({
                country_code: z
                  .string()
                  .optional()
                  .describe(
                    "ISO 3166-1 alpha-2 country code; omitted when the deployment region is unknown.",
                  ),
                region: z
                  .string()
                  .describe("Region identifier for an available deployment."),
              }),
            )
            .describe("Regions containing available model deployments."),
          deployment_region: z
            .string()
            .optional()
            .describe(
              "Country shared by all advertised datacenters; omitted if the country is unknown or deployments span countries.",
            ),
          compliance: z
            .object({
              zdr: z
                .boolean()
                .describe(
                  "Whether the provider catalog advertises zero data retention.",
                ),
              hipaa: z
                .boolean()
                .describe(
                  "Whether the provider catalog advertises HIPAA compliance.",
                ),
            })
            .describe("Compliance flags advertised by the gateway."),
        }),
      )
      .describe(
        "Model catalog entries visible through the authenticated gateway.",
      ),
  })
  .openapi("InferenceModelList");
