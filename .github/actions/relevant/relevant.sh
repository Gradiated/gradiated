#!/usr/bin/env bash
# Required checks must report even when a pull request does not touch a workflow,
# so workflows run on every pull request and skip their jobs here instead. The
# workflow's own push paths stay the single list of what is relevant.
set -euo pipefail

jobs=$(yq '.jobs | keys | .[] | select(. != "changes" and . != "passed")' "$WORKFLOW" | sort)
gated=$(yq '.jobs.passed.needs[] | select(. != "changes")' "$WORKFLOW" | sort)
if [[ "$jobs" != "$gated" ]]; then
  echo "Every job in $WORKFLOW must be listed in jobs.passed.needs so the gate covers it" >&2
  diff <(echo "$jobs") <(echo "$gated") >&2 || true
  exit 1
fi

if [[ "$EVENT" != pull_request ]]; then
  echo relevant=true >>"$GITHUB_OUTPUT"
  if [[ -n "${SCOPES:-}" ]]; then
    if [[ "$EVENT" == push && -n "${BEFORE:-}" && "$BEFORE" != 0000000000000000000000000000000000000000 ]]; then
      git diff --name-only --no-renames "$BEFORE" "$HEAD" |
        python3 "$GITHUB_ACTION_PATH/select.py" "$SCOPES" "$WORKFLOW"
    else
      python3 "$GITHUB_ACTION_PATH/select.py" "$SCOPES" "$WORKFLOW" --force
    fi
  fi
  exit 0
fi

mapfile -t patterns < <(yq '.on.push.paths[]' "$WORKFLOW")
((${#patterns[@]})) || {
  echo "$WORKFLOW has no push paths" >&2
  exit 1
}
# A failed lookup must fail the check, never read as "nothing changed".
changed=$(gh api --paginate "repos/$REPOSITORY/pulls/$PULL_REQUEST/files" \
  --jq '.[] | .filename, (.previous_filename // empty)')
if [[ -n "${SCOPES:-}" ]]; then
  printf '%s\n' "$changed" |
    python3 "$GITHUB_ACTION_PATH/select.py" "$SCOPES" "$WORKFLOW"
fi
mapfile -t files <<<"$changed"

relevant=false
for file in "${files[@]}"; do
  for pattern in "${patterns[@]}"; do
    # Unquoted: a glob match where "*" may also cross "/", so it can only over-select.
    # shellcheck disable=SC2053
    if [[ $file == $pattern ]]; then
      relevant=true
      break 2
    fi
  done
done
echo "relevant=$relevant" >>"$GITHUB_OUTPUT"
