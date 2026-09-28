#!/usr/bin/env bash
set -euo pipefail
while [[ ! -f ${NOMAD_ALLOC_DIR:?}/runtime-starting ]]; do
  sleep 1
done
exec "$NOMAD_ALLOC_DIR/runtime/desmondd" --observe
