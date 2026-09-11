export type ConnectClient =
  | "openai-python"
  | "openai-node"
  | "anthropic-python"
  | "anthropic-node"
  | "curl-openai"
  | "curl-anthropic"
  | "claude-code"
  | "codex"
  | "opencode";

interface SnippetInput {
  gradiatedKey: string;
  taskSlug: string;
}

export const connectSnippet = (
  client: ConnectClient,
  { gradiatedKey, taskSlug }: SnippetInput,
): string => {
  switch (client) {
    case "openai-python":
      return `import os
from openai import OpenAI

client = OpenAI(
    base_url="https://api.gradiated.com",
    api_key=os.environ["OPENAI_API_KEY"],  # your existing provider key
    default_headers={
        "x-gradiated-api-key": os.environ["GRADIATED_API_KEY"],
        "x-gradiated-task": "${taskSlug}",
    },
)`;
    case "openai-node":
      return `import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "https://api.gradiated.com",
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
    base_url="https://api.gradiated.com",
    api_key=os.environ["ANTHROPIC_API_KEY"],  # your existing provider key
    default_headers={
        "x-gradiated-api-key": os.environ["GRADIATED_API_KEY"],
        "x-gradiated-task": "${taskSlug}",
    },
)`;
    case "anthropic-node":
      return `import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic({
  baseURL: "https://api.gradiated.com",
  apiKey: process.env.ANTHROPIC_API_KEY, // your existing provider key
  defaultHeaders: {
    "x-gradiated-api-key": process.env.GRADIATED_API_KEY,
    "x-gradiated-task": "${taskSlug}",
  },
});`;
    case "curl-openai":
      return `curl https://api.gradiated.com/v1/chat/completions \\
  -H "Authorization: Bearer $OPENAI_API_KEY" \\
  -H "x-gradiated-api-key: $GRADIATED_API_KEY" \\
  -H "x-gradiated-task: ${taskSlug}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"Hello"}]}'`;
    case "curl-anthropic":
      return `curl https://api.gradiated.com/v1/messages \\
  -H "x-api-key: $ANTHROPIC_API_KEY" \\
  -H "anthropic-version: 2023-06-01" \\
  -H "x-gradiated-api-key: $GRADIATED_API_KEY" \\
  -H "x-gradiated-task: ${taskSlug}" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"claude-sonnet-4-5","max_tokens":256,"messages":[{"role":"user","content":"Hello"}]}'`;
    case "claude-code":
      return `# ~/.zshrc (or the shell you launch Claude Code from)
export ANTHROPIC_BASE_URL="https://api.gradiated.com"
export ANTHROPIC_CUSTOM_HEADERS="x-gradiated-api-key: ${gradiatedKey}
x-gradiated-task: ${taskSlug}"`;
    case "codex":
      return `# ~/.codex/config.toml
model_provider = "gradiated"

[model_providers.gradiated]
name = "Gradiated"
base_url = "https://api.gradiated.com/v1"
env_key = "OPENAI_API_KEY"
env_http_headers = { "x-gradiated-api-key" = "GRADIATED_API_KEY" }
http_headers = { "x-gradiated-task" = "${taskSlug}" }

# then: export GRADIATED_API_KEY="${gradiatedKey}"`;
    case "opencode":
      return `// opencode.json
{
  "provider": {
    "gradiated": {
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "https://api.gradiated.com/v1",
        "apiKey": "{env:OPENAI_API_KEY}",
        "headers": {
          "x-gradiated-api-key": "${gradiatedKey}",
          "x-gradiated-task": "${taskSlug}"
        }
      }
    }
  }
}`;
  }
};
