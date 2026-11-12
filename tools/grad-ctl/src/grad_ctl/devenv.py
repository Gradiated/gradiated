"""Shared development credentials from gradiated/dev/env.

A value comes from the environment (an ignored .env loaded as AGENTS.md
describes) or, if unset, from the secret read with the AWS profile in
AWS_PROFILE (default gradiated-readonly). Values are never printed.
"""

from __future__ import annotations

import base64
import functools
import json
import os
import shutil
import subprocess

from .core import CliError

SECRET_ID = 'gradiated/dev/env'
REGION = 'us-east-1'


@functools.lru_cache(maxsize=None)
def dev_env() -> dict[str, str]:
    if not shutil.which('aws'):
        return {}
    result = subprocess.run(['aws', '--profile', os.environ.get('AWS_PROFILE', 'gradiated-readonly'),
                             '--region', REGION, 'secretsmanager', 'get-secret-value', '--secret-id',
                             SECRET_ID, '--query', 'SecretString', '--output', 'text'],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
    return json.loads(result.stdout) if result.returncode == 0 else {}


def secret(name: str) -> str:
    value = os.environ.get(name) or dev_env().get(name)
    if not value:
        raise CliError(f'{name} is not set and {SECRET_ID} could not be read', 'credentials_missing',
                       'run `grad-ctl env build` or `grad-ctl aws login`, then retry')
    return base64.b64decode(value).decode() if name.endswith('_B64') else value
