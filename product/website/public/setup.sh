#!/usr/bin/env bash
# Gradiated coding-agent setup.
#
# Configures OpenCode to use the Gradiated inference API. Detects Codex and
# Claude Code and reports their support status instead of writing broken
# configuration.
#
# Usage:
#   curl -fsSL https://gradiated.com/setup.sh | bash
#
# The API key is read from GRADIATED_API_KEY or prompted for. The key is
# never written to disk by this script; OpenCode reads it from the
# environment at runtime.
#
# Compatible with macOS bash 3.2. Reads prompts from /dev/tty so it also
# works when piped: curl -fsSL ... | bash
set -euo pipefail

API_BASE_URL="${GRADIATED_API_BASE_URL:-https://api.gradiated.com}"
OPENCODE_CONFIG_DIR="${OPENCODE_CONFIG_DIR:-$HOME/.config/opencode}"
OPENCODE_CONFIG_FILE="$OPENCODE_CONFIG_DIR/opencode.json"
PROVIDER_ID="gradiated"
CONFIG_SCHEMA="https://opencode.ai/config.json"

say() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# read_prompt VAR PROMPT  (reads from /dev/tty when available)
read_prompt() {
  __var="$1"; __prompt="$2"
  printf '%s' "$__prompt" >&2
  if [[ -r /dev/tty ]]; then
    IFS= read -r "$__var" < /dev/tty
  else
    IFS= read -r "$__var"
  fi
}

# read_secret VAR PROMPT  (hidden input)
read_secret() {
  __var="$1"; __prompt="$2"
  printf '%s' "$__prompt" >&2
  if [[ -r /dev/tty ]]; then
    stty_orig="$(stty -g < /dev/tty 2>/dev/null || true)"
    [[ -n "$stty_orig" ]] && stty -echo < /dev/tty
    IFS= read -r "$__var" < /dev/tty || true
    [[ -n "$stty_orig" ]] && stty "$stty_orig" < /dev/tty
  else
    IFS= read -r "$__var" || true
  fi
  printf '\n' >&2
}

for tool in curl jq; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool is required. Install it and run this again."
done

say ""
say "Gradiated coding-agent setup"
say "----------------------------"
if command -v opencode >/dev/null 2>&1; then
  say "  opencode  found"
else
  say "  opencode  not found"
fi
command -v codex  >/dev/null 2>&1 && say "  codex     found (not configurable yet - see below)"
command -v claude >/dev/null 2>&1 && say "  claude    found (not configurable yet - see below)"
say ""

if ! command -v opencode >/dev/null 2>&1; then
  say "OpenCode is not installed. Install it first:"
  say "  curl -fsSL https://opencode.ai/install | bash"
  say "Then run this script again."
  exit 1
fi

# --- API key -------------------------------------------------------------------

API_KEY="${GRADIATED_API_KEY:-}"
if [[ -z "$API_KEY" ]]; then
  read_secret API_KEY "Enter your Gradiated API key (input hidden): "
  [[ -n "${API_KEY:-}" ]] || die "no API key provided. Create one at https://console.gradiated.com"
fi

# --- Verify the key and read the model catalog ---------------------------------

say "Verifying the key against $API_BASE_URL ..."
catalog="$(curl -fsS --max-time 30 \
  -H "Authorization: Bearer $API_KEY" \
  "$API_BASE_URL/models")" || die "could not fetch $API_BASE_URL/models. Check the key and your network."

model_ids="$(printf '%s' "$catalog" | jq -r '.data[]?.id' | grep -v '^$' || true)"
[[ -n "$model_ids" ]] || die "the catalog response contains no models."

model_count="$(printf '%s\n' "$model_ids" | wc -l | tr -d ' ')"
say "Available models:"
i=1
while IFS= read -r id; do
  printf '  %d. %s\n' "$i" "$id"
  i=$((i + 1))
done <<EOF
$model_ids
EOF
say ""

default_choice=1
read_prompt choice "Model to use as the default [1-$model_count, enter for 1]: "
if [[ -n "${choice:-}" ]]; then
  case "$choice" in
    ''|*[!0-9]*) die "invalid model choice: $choice" ;;
  esac
  (( choice >= 1 && choice <= model_count )) || die "invalid model choice: $choice"
  default_choice="$choice"
fi
default_model="$(printf '%s\n' "$model_ids" | sed -n "${default_choice}p")"
say "Using model: $default_model"
say ""

# --- Build the models map with limits from the catalog -------------------------

models_json="$(printf '%s' "$catalog" | jq '
  [ .data[] | . as $m
    | (if ($m.input_modalities[0].supported_inputs.max_context_length.value // null) != null
        and ($m.output_modalities[0].max_length.value // null) != null
       then {
         ($m.id): {
           name: ($m.name // $m.id),
           limit: {
             context: $m.input_modalities[0].supported_inputs.max_context_length.value,
             output: $m.output_modalities[0].max_length.value
           }
         }
       }
       else { ($m.id): { name: ($m.name // $m.id) } }
       end)
  ] | add // {}
')"

provider_block="$(jq -cn \
  --arg base "$API_BASE_URL" \
  --argjson models "$models_json" \
  '{
    npm: "@ai-sdk/openai-compatible",
    name: "Gradiated",
    options: { baseURL: $base, apiKey: "{env:GRADIATED_API_KEY}" },
    models: $models
  }')"

# --- Merge the provider into the OpenCode user config ---------------------------

mkdir -p "$OPENCODE_CONFIG_DIR"
tmp_file="$OPENCODE_CONFIG_FILE.tmp"
if [[ -f "$OPENCODE_CONFIG_FILE" ]]; then
  backup="$OPENCODE_CONFIG_FILE.bak.$(date -u +%Y%m%dT%H%M%SZ)"
  cp "$OPENCODE_CONFIG_FILE" "$backup"
  say "Backed up the existing config to $backup"
  jq --arg id "$PROVIDER_ID" --argjson block "$provider_block" \
    '.provider = ((.provider // {}) + {($id): $block})' \
    "$OPENCODE_CONFIG_FILE" > "$tmp_file"
else
  jq -n \
    --arg schema "$CONFIG_SCHEMA" \
    --arg id "$PROVIDER_ID" \
    --argjson block "$provider_block" \
    '{($schema): "https://opencode.ai/config.json"}
     | .provider = {($id): $block}' > "$tmp_file"
fi
mv "$tmp_file" "$OPENCODE_CONFIG_FILE"
say "Wrote the Gradiated provider to $OPENCODE_CONFIG_FILE"

# --- Default model ---------------------------------------------------------------

if jq -e 'has("model")' "$OPENCODE_CONFIG_FILE" >/dev/null 2>&1; then
  existing_model="$(jq -r '.model' "$OPENCODE_CONFIG_FILE")"
  say "Keeping the existing default model: $existing_model"
else
  jq --arg model "gradiated/$default_model" '.model = $model' \
    "$OPENCODE_CONFIG_FILE" > "$tmp_file"
  mv "$tmp_file" "$OPENCODE_CONFIG_FILE"
  say "Default model set to gradiated/$default_model"
fi

# --- Shell profile ----------------------------------------------------------------

if [[ -n "${GRADIATED_API_KEY:-}" ]]; then
  say "GRADIATED_API_KEY is already set in this shell; no profile change made."
else
  read_prompt answer "Add GRADIATED_API_KEY to your shell profile now? [y/N]: "
  if [[ "${answer:-}" == "y" || "${answer:-}" == "Y" ]]; then
    profile_target="$HOME/.bashrc"
    if [[ -n "${ZSH_VERSION:-}" || "${SHELL:-}" == */zsh ]]; then
      profile_target="$HOME/.zshrc"
    fi
    {
      say ""
      say "export GRADIATED_API_KEY=\"$API_KEY\""
    } >> "$profile_target"
    say "Added the export line to $profile_target. Run: source $profile_target"
  else
    say "Add this line to your shell profile yourself:"
    say '  export GRADIATED_API_KEY="..."'
  fi
fi

say ""
say "Done. Start OpenCode and run /models to pick the Gradiated model."

if command -v codex >/dev/null 2>&1; then
  say "Codex: not configurable yet. Codex custom providers require the Responses API; Gradiated serves Chat Completions. See https://gradiated.com/docs/codex/"
fi
if command -v claude >/dev/null 2>&1; then
  say "Claude Code: not configurable yet. Claude Code speaks the Anthropic Messages API; Gradiated serves Chat Completions. See https://gradiated.com/docs/codex/"
fi
