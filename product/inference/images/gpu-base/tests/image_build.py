import os
import re
import time
from pathlib import Path
import shlex
import subprocess
import tempfile
from urllib.parse import urlsplit

# CI sets these: a builder with a persistent layer cache (depot build --load), and an
# Ubuntu mirror, so a cold build does not depend on archive.ubuntu.com's throughput.
BUILD = shlex.split(os.environ.get('GPU_BASE_TEST_BUILD', 'docker build'))
APT_MIRROR = os.environ.get('GPU_BASE_TEST_APT_MIRROR', '')


def with_mirror(lines):
    if not APT_MIRROR:
        return lines
    # The images' own steps then switch the sources to HTTPS, which the mirror serves.
    rewrite = (f"RUN sed -i -e 's|http://archive.ubuntu.com/ubuntu|{APT_MIRROR}|' "
               f"-e 's|http://security.ubuntu.com/ubuntu|{APT_MIRROR}|' /etc/apt/sources.list.d/ubuntu.sources")
    result = []
    for line in lines:
        result.append(line)
        if line.startswith('FROM ') and 'ubuntu' in line.split()[1]:
            result.append(rewrite)
    return result


def build_image(tag, lines, context, timeout=1200):
    with tempfile.TemporaryDirectory() as directory:
        dockerfile = Path(directory) / 'Dockerfile'
        try:
            deadline = time.monotonic() + timeout
            mirror = bool(APT_MIRROR)
            mirror_url = urlsplit(APT_MIRROR)
            mirror_fetch = r'Failed to fetch https?://' + re.escape(mirror_url.netloc + mirror_url.path.rstrip('/')) + r'(?:/|\s)'
            uncached = False
            for attempt in range(3):
                dockerfile.write_text('\n'.join(with_mirror(lines) if mirror else lines) + '\n')
                flags = ['--no-cache'] if uncached else []
                result = subprocess.run([*BUILD, *flags, '--progress=plain', '--platform', 'linux/amd64', '-t', tag,
                                         '-f', str(dockerfile), str(context)],
                                        text=True, capture_output=True, timeout=max(0.001, deadline - time.monotonic()))
                if not result.returncode:
                    break
                if not uncached and re.search(r'snapshot .+ does not exist: not found', result.stderr):
                    uncached = True
                    print('Builder cache snapshot is missing; retrying once without cached layers.', flush=True)
                elif mirror and re.search(mirror_fetch, result.stderr) and re.search(
                        r'connection timed out|Network is unreachable|Temporary failure resolving', result.stderr, re.I):
                    mirror = False
                    print('The CI apt mirror is unreachable; retrying once with the original Ubuntu sources.', flush=True)
                else:
                    break
        except subprocess.TimeoutExpired as error:
            output = error.stderr.decode(errors='replace') if isinstance(error.stderr, bytes) else error.stderr or ''
            raise AssertionError(f'Building {tag} timed out:\n{output[-5000:]}') from None
    if result.returncode:
        raise AssertionError(f'Building {tag} failed:\n{result.stderr[-5000:]}')
