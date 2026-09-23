const API_BASE_URL = "https://api.gradiated.com";

export type ConnectClient =
  | "openai-python"
  | "openai-node"
  | "anthropic-python"
  | "anthropic-node"
  | "curl-openai"
  | "curl-anthropic";

export const connectSnippet = (
  client: ConnectClient,
  taskSlug: string,
): string => {
  switch (client) {
    case "openai-python":
      return `import os
from openai import OpenAI

client = OpenAI(
    base_url="${API_BASE_URL}",
    api_key=os.environ["OPENAI_API_KEY"],  # your existing provider key
    default_headers={
        "x-gradiated-api-key": os.environ["GRADIATED_API_KEY"],
        "x-gradiated-task": "${taskSlug}",
    },
)`;
    case "openai-node":
      return `import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "${API_BASE_URL}",
  apiKey: process.env.OPENAI_API_KEY, // your existing provider key
  defaultHeaders: {
    "x-gradiated-api-key": process.env.GRADIATED_API_KEY,
    "x-gradiated-task": "${taskSlug}",
  },
});`;
    case "anthropic-python":
      return `import os
from anthropic import Anthropic

client = Anthropic(
    base_url="${API_BASE_URL}",
    api_key=os.environ["ANTHROPIC_API_KEY"],  # your existing provider key
    default_headers={
        "x-gradiated-api-key": os.environ["GRADIATED_API_KEY"],
        "x-gradiated-task": "${taskSlug}",
    },
)`;
    case "anthropic-node":
      return `import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic({
  baseURL: "${API_BASE_URL}",
  apiKey: process.env.ANTHROPIC_API_KEY, // your existing provider key
  defaultHeaders: {
    "x-gradiated-api-key": process.env.GRADIATED_API_KEY,
    "x-gradiated-task": "${taskSlug}",
  },
});`;
    case "curl-openai":
      return `curl ${API_BASE_URL}/v1/chat/completions \\
  -H "Authorization: Bearer $OPENAI_API_KEY" \\
  -H "x-gradiated-api-key: $GRADIATED_API_KEY" \\
  -H "x-gradiated-task: ${taskSlug}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"Hello"}]}'`;
    case "curl-anthropic":
      return `curl ${API_BASE_URL}/v1/messages \\
  -H "x-api-key: $ANTHROPIC_API_KEY" \\
  -H "anthropic-version: 2023-06-01" \\
  -H "x-gradiated-api-key: $GRADIATED_API_KEY" \\
  -H "x-gradiated-task: ${taskSlug}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"claude-sonnet-4-5","max_tokens":256,"messages":[{"role":"user","content":"Hello"}]}'`;
  }
};
