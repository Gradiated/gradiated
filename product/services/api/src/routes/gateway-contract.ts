import { z, type OpenAPIHono } from "@hono/zod-openapi";

import type { ApiEnvironment } from "../types.js";
import {
  chatRequest,
  chatResponse,
  messagesRequest,
  messagesResponse,
  responsesRequest,
  responsesResponse,
  catalogResponse,
} from "./gateway-schemas.js";
import { registerSystemOneContract } from "./systemone-contract.js";

const errors = {
  400: {
    description:
      "Invalid request, unsupported parameter, or context length exceeded. Errors use the endpoint's wire protocol.",
  },
  401: { description: "Missing or invalid workspace API key." },
  402: { description: "Insufficient prepaid balance." },
  404: { description: "Unknown or unavailable exact model." },
  413: { description: "Request exceeds the gateway body limit." },
  429: { description: "Admission or inference capacity exhausted." },
  503: {
    description: "Runtime, deployment, or gateway dependency unavailable.",
  },
};

// Registry entries describe Rust endpoints; they must not install Hono handlers.
export const registerGatewayContract = (app: OpenAPIHono<ApiEnvironment>) => {
  registerSystemOneContract(app);
  app.openAPIRegistry.registerComponent("securitySchemes", "InferenceApiKey", {
    type: "apiKey",
    in: "header",
    name: "x-api-key",
    description:
      "Workspace API key; alternatively use Authorization: Bearer. Authorization takes precedence when both are supplied.",
  });
  const security = [{ InferenceBearer: [] }, { InferenceApiKey: [] }];
  const operations = [
    {
      path: "/chat/completions",
      operationId: "chatCompletions",
      summary: "Create a chat completion",
      request: chatRequest,
      response: chatResponse,
      streaming: true,
      description:
        "OpenAI Chat Completions compatible inference. max_tokens and max_completion_tokens are mutually exclusive.",
    },
    {
      path: "/messages",
      operationId: "createMessage",
      summary: "Create a message",
      request: messagesRequest,
      response: messagesResponse,
      streaming: true,
      description:
        "Anthropic Messages compatible inference, translated by the gateway.",
    },
    {
      path: "/responses",
      operationId: "createResponse",
      summary: "Create a response",
      request: responsesRequest,
      response: responsesResponse,
      streaming: true,
      description:
        "OpenAI Responses compatible inference. Stateless requests only: store=true, background=true, previous_response_id, conversation and prompt references are unsupported.",
    },
    {
      path: "/messages/count_tokens",
      operationId: "countMessageTokens",
      summary: "Count message input tokens",
      request: messagesRequest
        .omit({ max_tokens: true, stream: true, service_tier: true })
        .openapi("CountMessageTokensRequest"),
      response: z
        .object({
          input_tokens: z
            .number()
            .int()
            .nonnegative()
            .describe(
              "Number of input tokens after protocol translation and model-specific tokenization; no output is generated.",
            ),
        })
        .openapi("MessageTokenCount"),
      streaming: false,
      description:
        "Count tokens using the selected model's tokenizer without generating a completion.",
    },
  ];
  const references: Record<string, string> = {
    "/chat/completions":
      "https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create",
    "/messages": "https://platform.claude.com/docs/en/api/messages/create",
    "/responses":
      "https://developers.openai.com/api/reference/resources/responses/methods/create",
    "/messages/count_tokens":
      "https://platform.claude.com/docs/en/api/messages/count_tokens",
  };

  for (const operation of operations) {
    app.openAPIRegistry.registerPath({
      method: "post",
      path: `/v1${operation.path}`,
      operationId: operation.operationId,
      tags: ["Inference"],
      summary: operation.summary,
      externalDocs: {
        description:
          "Upstream protocol reference. Gradiated supports the fields and model capabilities documented here, not every upstream feature.",
        url: references[operation.path]!,
      },
      security,
      description: `${operation.description} Requires an exact hosted model and a workspace API key. Supported parameters depend on the model catalog. Also available at ${operation.path}.`,
      request: {
        body: {
          required: true,
          content: { "application/json": { schema: operation.request } },
        },
      },
      responses: {
        200: {
          description: operation.streaming
            ? "Protocol-compatible JSON, or server-sent events when stream=true."
            : "Input token count.",
          content: {
            "application/json": { schema: operation.response },
            ...(operation.streaming
              ? {
                  "text/event-stream": {
                    schema: z
                      .string()
                      .describe(
                        "Incremental events in the endpoint's wire protocol; Chat Completions terminates with data: [DONE].",
                      ),
                  },
                }
              : {}),
          },
        },
        ...errors,
      },
    });
  }
  for (const path of ["/v1/models", "/models"]) {
    app.openAPIRegistry.registerPath({
      method: "get",
      path,
      operationId:
        path === "/models" ? "listInferenceModelsAlias" : "listInferenceModels",
      tags: ["Models"],
      summary: "List inference models",
      security,
      description:
        "Authenticated gateway catalog with exact model IDs, readiness, capabilities and pricing. /models and /v1/models are aliases. This differs from the management catalog at /api/v1/models.",
      responses: {
        200: {
          description: "Inference model catalog.",
          content: { "application/json": { schema: catalogResponse } },
        },
        401: errors[401],
        503: errors[503],
      },
    });
  }
};
