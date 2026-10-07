#!/usr/bin/env bash
set -euo pipefail

if [[ "$EVENT_NAME" == pull_request ]] &&
   git diff --quiet HEAD^ HEAD -- . \
     ':!product/services/console/screenshots/*.png' \
     ':!product/website/screenshots/*.png'; then
  echo 'capture=false' >> "$GITHUB_OUTPUT"
else
  echo 'capture=true' >> "$GITHUB_OUTPUT"
fi
