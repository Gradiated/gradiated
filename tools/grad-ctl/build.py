#!/usr/bin/env python3
"""Build grad-ctl as one file: a Python zipapp that runs on any machine with python3 >= 3.10.

  python3 tools/grad-ctl/build.py                    # .agents/runtime/grad-ctl/grad-ctl
  python3 tools/grad-ctl/build.py --install          # ~/.local/bin/grad-ctl
  python3 tools/grad-ctl/build.py --output PATH

The file has no dependencies beyond the standard library and needs no checkout:
copy it to a VM or another machine and run it. Commands that work on the
repository find the checkout from the working directory or GRAD_CTL_REPO.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipapp
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = HERE / 'src' / 'grad_ctl'


def revision() -> str:
    result = subprocess.run(['git', 'describe', '--always', '--dirty', '--abbrev=12'], cwd=ROOT,
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else 'unknown'


def build(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        package = Path(directory) / 'grad_ctl'
        shutil.copytree(SOURCE, package, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '_build.py'))
        (package / '_build.py').write_text(f'BUILD = {revision()!r}\n')
        temporary = output.with_name(f'.{output.name}.tmp')
        zipapp.create_archive(directory, temporary, interpreter='/usr/bin/env python3',
                              main='grad_ctl.cli:main', compressed=True)
        os.chmod(temporary, 0o755)
        os.replace(temporary, output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=ROOT / '.agents/runtime/grad-ctl/grad-ctl')
    parser.add_argument('--install', action='store_true', help='write ~/.local/bin/grad-ctl')
    args = parser.parse_args()
    target = Path.home() / '.local/bin/grad-ctl' if args.install else args.output
    built = build(target.expanduser())
    print(f'built {built} ({revision()})')
    if args.install and str(built.parent) not in os.environ.get('PATH', '').split(os.pathsep):
        print(f'add {built.parent} to PATH', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
