#!/usr/bin/env bash
set -euo pipefail
# Build the release archive from cached dependencies and current launch files.
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
  -C /bundle -I "pigz -p 4" -cf /runtime.tar.gz .
