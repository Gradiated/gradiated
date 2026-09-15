#!/usr/bin/env bash
set -euo pipefail
# Archive the pinned distribution without making a second package-tree copy.
python3 -c 'import sys; assert sys.version_info[:2] == (3, 12)'
stdlib=$(python3 -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')
packages=$(python3 -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
install -d /bundle/python/bin /bundle/python/lib/python3.12
ln -s "$(readlink -f "$(command -v python3)")" /bundle/python/bin/python3
for entry in "$stdlib"/*; do
  case "${entry##*/}" in
    site-packages|dist-packages|__pycache__) continue ;;
  esac
  ln -s "$entry" "/bundle/python/lib/python3.12/${entry##*/}"
done
ln -s "$packages" /bundle/python/lib/python3.12/site-packages
# Dereference links so the archive has no paths into the builder filesystem.
tar --dereference --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
  --exclude=__pycache__ --exclude='*.pyc' -C /bundle -czf /runtime.tar.gz .
