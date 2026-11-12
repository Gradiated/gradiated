"""The command model every gradctl command shares: metadata, results, errors and output.

Agents rely on three guarantees:

- With --json (or GRADCTL_JSON=1), stdout holds exactly one JSON document, the
  envelope below, and everything else (progress, subprocess output) goes to
  stderr.
- Exit codes are stable: see EXIT_CODES.
- No command prompts. A command that needs a person (a browser sign-in) says so
  with interactive=true in `gradctl commands`.

Envelope:

  {"ok": true,  "command": "compute search", "data": ...}
  {"ok": false, "command": "compute search", "data": ..., "error": {"code": ..., "message": ..., "hint": ...}}
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

EXIT_CODES = {
    0: 'ok',
    1: 'failed: the command ran and did not succeed',
    2: 'usage: bad arguments; nothing was done',
    3: 'tailnet_required: this machine is not connected to the Gradiated tailnet',
    4: 'repo_required: the command needs a Gradiated checkout',
    5: 'dependency_missing: a required tool (aws, kubectl, nebius, ...) is not installed',
    130: 'interrupted',
}


class CliError(Exception):
    """A failure the envelope reports with a stable code."""

    def __init__(self, message: str, code: str = 'failed', hint: str | None = None, exit_code: int = 1,
                 data: Any = None):
        super().__init__(message)
        self.message, self.code, self.hint, self.exit_code, self.data = message, code, hint, exit_code, data


class UsageError(CliError):
    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message, 'usage', hint, 2)


class DependencyMissing(CliError):
    def __init__(self, tool: str, hint: str | None = None):
        super().__init__(f'{tool} is not installed', 'dependency_missing', hint, 5)


@dataclass
class Meta:
    """What a command does, so an agent can decide whether and how to run it.

    effects: read (no changes), write (changes something, safe to rerun) or
      destructive (deletes or wipes something).
    network: reaches the tailnet or a remote API. In GitHub Actions, which is not
      on the tailnet, only commands with network=False run.
    repo: needs a Gradiated checkout.
    tailnet: False only for the commands that report or establish the tailnet
      connection, and for catalog commands.
    forwards_args: arguments after the command go unchanged to a repository tool.
    """

    summary: str
    effects: str = 'read'
    network: bool = True
    repo: bool = False
    tailnet: bool = True
    interactive: bool = False
    requires: tuple[str, ...] = ()
    forwards_args: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {'summary': self.summary, 'effects': self.effects, 'network': self.network, 'repo': self.repo,
                'tailnet': self.tailnet, 'interactive': self.interactive, 'requires': list(self.requires),
                'forwards_args': self.forwards_args}


@dataclass
class Result:
    data: Any = None
    text: str | None = None
    ok: bool = True
    exit_code: int = 0
    error: str | None = None
    error_code: str = 'failed'


@dataclass
class Context:
    args: argparse.Namespace
    command: str
    json: bool
    _repo: Any = field(default=None, repr=False)

    def repo(self):
        if self._repo is None:
            from .repo import find_root
            self._repo = find_root()
        return self._repo

    @staticmethod
    def log(message: str) -> None:
        print(message, file=sys.stderr, flush=True)


Handler = Callable[[Context], 'Result | None']


class Parser(argparse.ArgumentParser):
    """Raises UsageError instead of printing usage and exiting, so --json can report it.

    Abbreviations are off so an option meant for a forwarded repository tool is
    never taken as a prefix of one of gradctl's own (`--j` for `--json`).
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('allow_abbrev', False)
        super().__init__(*args, **kwargs)

    def error(self, message):  # noqa: D401 - argparse API
        raise UsageError(message, hint=f'run `{self.prog} --help`')


def leaf(subparsers, name: str, run: Handler, meta: Meta, common: argparse.ArgumentParser, **kwargs):
    """Add a runnable command."""
    parser = subparsers.add_parser(name, help=meta.summary, description=kwargs.pop('description', meta.summary),
                                   parents=[common], formatter_class=argparse.RawDescriptionHelpFormatter,
                                   **kwargs)
    parser.set_defaults(run=run, meta=meta, command_path=parser.prog.removeprefix('gradctl '))
    return parser


def group(subparsers, name: str, summary: str):
    """Add a command group, returning its subparsers."""
    parser = subparsers.add_parser(name, help=summary, description=summary)
    parser.add_argument('--json', action='store_true', default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    parser.set_defaults(group_parser=parser)
    return parser.add_subparsers(dest=f'{name}_command', metavar='COMMAND')


def envelope(command: str, result: Result) -> dict[str, Any]:
    body: dict[str, Any] = {'ok': result.ok, 'command': command, 'data': result.data}
    if not result.ok:
        body['error'] = {'code': result.error_code, 'message': result.error or 'failed', 'hint': None}
    return body


def error_envelope(command: str, error: CliError) -> dict[str, Any]:
    return {'ok': False, 'command': command, 'data': error.data,
            'error': {'code': error.code, 'message': error.message, 'hint': error.hint}}


def emit_json(document: dict[str, Any]) -> None:
    print(json.dumps(document, indent=1, default=str), flush=True)


@contextlib.contextmanager
def stdout_to_stderr():
    """Send everything written to stdout, by Python or a subprocess, to stderr.

    Keeps stdout for the one JSON envelope even when a command prints progress
    or runs a tool such as `aws sso login` that writes to its inherited stdout.
    """
    sys.stdout.flush()
    try:
        descriptor = sys.stdout.fileno()
    except (AttributeError, OSError, ValueError):
        with contextlib.redirect_stdout(sys.stderr):
            yield
        return
    saved = os.dup(descriptor)
    os.dup2(sys.stderr.fileno(), descriptor)
    try:
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved, descriptor)
        os.close(saved)


def system_exit_error(error: SystemExit) -> CliError | None:
    """Turn a sys.exit() from command code into a CliError, or None for success."""
    code = error.code
    if code is None or code == 0:
        return None
    if isinstance(code, int):
        return CliError(f'exited with status {code}', exit_code=code)
    return CliError(str(code))
