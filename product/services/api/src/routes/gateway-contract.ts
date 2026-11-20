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
  retryAfterHeaders,
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
  429: {
    description: "Admission or inference capacity exhausted.",
    headers: retryAfterHeaders,
  },
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
      summary: "Chat Completions",
      request: chatRequest,
      response: chatResponse,
      streaming: true,
      description: "OpenAI-compatible chat completions.",
    },
    {
      path: "/messages",
      operationId: "createMessage",
      summary: "Messages",
      request: messagesRequest,
      response: messagesResponse,
      streaming: true,
      description: "Anthropic-compatible messages.",
    },
    {
      path: "/responses",
      operationId: "createResponse",
      summary: "Responses",
      request: responsesRequest,
      response: responsesResponse,
      streaming: true,
      description:
        "OpenAI-compatible responses. Only stateless requests are supported.",
    },
    {
      path: "/messages/count_tokens",
      operationId: "countMessageTokens",
      summary: "Count tokens",
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
      description: "Counts the input tokens of a Messages request.",
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
        description: "Upstream API reference",
        url: references[operation.path]!,
      },
      security,
      description: `${operation.description} Also served at ${operation.path}.`,
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
  app.openAPIRegistry.registerPath({
    method: "get",
    path: "/v1/models",
    operationId: "listInferenceModels",
    tags: ["Models"],
    summary: "List models",
    security,
    description:
      "Lists the models you can call, with prices and capabilities. Also served at /models.",
    responses: {
      200: {
        description: "Inference model catalog.",
        content: { "application/json": { schema: catalogResponse } },
      },
      401: errors[401],
      503: errors[503],
    },
  });
};
