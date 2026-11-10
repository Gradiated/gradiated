#!/usr/bin/env bash
# serve.sh <port> <arm: opus|kimi>
set -euo pipefail
cd /root/saltfish/editor-lek/studio
set -a; . ./.env; set +a
export MODE=local BRAND=acme ANTHROPIC_BASE_URL=http://127.0.0.1:8899 ANTHROPIC_API_KEY=router-local
export PUPPETEER_EXECUTABLE_PATH=/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome
export STUDIO_READY_MAIL=off CLIPS_GC=off
# No Gemini key here: the Gemini seats run on Sonnet 5 in BOTH arms.
export V2_MODEL_SUMMARY=claude-sonnet-5 V2_MODEL_SCENES=claude-sonnet-5 V2_MODEL_ASK=claude-sonnet-5 V2_MODEL_LOCATE=claude-sonnet-5 V2_MODEL_DESCRIBE=claude-sonnet-5
if [ "$2" = kimi ]; then export V2_MODEL_DIRECTOR=claude-kimi-k3-1-pro V2_MODEL_BUILD=claude-kimi-k3-1-pro; fi
exec mise exec node@24 -- npx vite --port "$1" --strictPort
