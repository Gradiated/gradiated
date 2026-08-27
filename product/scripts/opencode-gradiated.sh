#!/usr/bin/env bash
set -euo pipefail

for command_name in aws jq opencode; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf '%s is required.\n' "${command_name}" >&2
    exit 1
  fi
done

if [[ -z "${GRADIATED_OPENCODE_KEY:-}" ]]; then
  secret_json="$(aws secretsmanager get-secret-value \
    --secret-id gradiated/prod/integrations/openrouter-provider \
    --query SecretString \
    --output text)"
  GRADIATED_OPENCODE_KEY="$(
    printf '%s' "${secret_json}" |
      jq -er '.OPENROUTER_API_KEY | strings | select(length > 0)'
  )"
  unset secret_json
fi

OPENCODE_CONFIG_CONTENT="$(jq -cn '{
  model: "gradiated/z-ai/glm-5.3-flash",
  provider: {
    gradiated: {
      npm: "@ai-sdk/openai-compatible",
      name: "Gradiated",
      options: {
        baseURL: "https://api.gradiated.com/openai/v1",
        apiKey: "{env:GRADIATED_OPENCODE_KEY}"
      },
      models: {
        "z-ai/glm-5.3-flash": {
          name: "GLM 5.3 Flash",
          reasoning: true,
          interleaved: {field: "reasoning_content"},
          limit: {context: 1048576, output: 131072}
        }
      }
    }
  }
}')"

export GRADIATED_OPENCODE_KEY OPENCODE_CONFIG_CONTENT
export OPENCODE_DISABLE_AUTOUPDATE=true

exec opencode --model gradiated/z-ai/glm-5.3-flash "$@"
