#!/usr/bin/env bash
set -euo pipefail
# Copy the pinned distribution. Do not resolve new package versions at build time.
python3 -c 'import sys; assert sys.version_info[:2] == (3, 12)'
stdlib=$(python3 -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')
packages=$(python3 -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
install -d /bundle/python/bin /bundle/python/lib/python3.12/site-packages
cp -L "$(command -v python3)" /bundle/python/bin/python3
cp -aL "$stdlib/." /bundle/python/lib/python3.12/
cp -aL "$packages/." /bundle/python/lib/python3.12/site-packages/
# Remove bytecode caches; the runtime user can regenerate them.
find /bundle -type d -name __pycache__ -prune -exec rm -rf {} +
