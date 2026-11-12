#!/usr/bin/env python3
"""Build gradctl as one file: a Python zipapp that runs on any machine with python3 >= 3.10.

  python3 tools/gradctl/build.py                    # .agents/runtime/gradctl/gradctl
  python3 tools/gradctl/build.py --install          # ~/.local/bin/gradctl
  python3 tools/gradctl/build.py --output PATH

The file has no dependencies beyond the standard library and needs no checkout:
copy it to a VM or another machine and run it. Commands that work on the
repository find the checkout from the working directory or GRADCTL_REPO.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipapp
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = HERE / 'src' / 'gradctl'


def revision() -> str:
    result = subprocess.run(['git', 'describe', '--always', '--dirty', '--abbrev=12'], cwd=ROOT,
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else 'unknown'


def build(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        package = Path(directory) / 'gradctl'
        shutil.copytree(SOURCE, package, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '_build.py'))
        (package / '_build.py').write_text(f'BUILD = {revision()!r}\n')
        temporary = output.with_name(f'.{output.name}.tmp')
        zipapp.create_archive(directory, temporary, interpreter='/usr/bin/env python3',
                              main='gradctl.cli:main', compressed=True)
        os.chmod(temporary, 0o755)
        os.replace(temporary, output)
    return output


def remove_old_name(directory: Path) -> None:
    """Delete a build installed under the CLI's old name, grad-ctl, so it cannot go stale."""
    old = directory / 'grad-ctl'
    try:
        with zipfile.ZipFile(old) as archive:
            ours = any(name.startswith('grad_ctl/') for name in archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return
    if ours:
        old.unlink()
        print(f'removed {old}, the old name of gradctl')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=ROOT / '.agents/runtime/gradctl/gradctl')
    parser.add_argument('--install', action='store_true', help='write ~/.local/bin/gradctl')
    args = parser.parse_args()
    target = Path.home() / '.local/bin/gradctl' if args.install else args.output
    built = build(target.expanduser())
    if args.install:
        remove_old_name(built.parent)
    print(f'built {built} ({revision()})')
    if args.install and str(built.parent) not in os.environ.get('PATH', '').split(os.pathsep):
        print(f'add {built.parent} to PATH', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
