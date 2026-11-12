"""gradctl: the Gradiated developer and agent CLI.

Every command needs this machine on the Gradiated tailnet. Run
`gradctl commands --json` for the full catalog: each command's arguments,
effects (read, write, destructive), requirements and whether it needs a person.
Pass --json for one machine-readable envelope on stdout.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import traceback

from . import BUILD, VERSION, devex, envfile, lease, repos, repotools, tailnet
from .compute import commands as compute
from .core import (EXIT_CODES, CliError, Context, Meta, Parser, Result, UsageError, emit_json, envelope,
                   error_envelope, leaf, stdout_to_stderr, system_exit_error)

EPILOG = """\
Agents: start with `gradctl commands --json`. With --json, stdout is exactly
one JSON document {"ok", "command", "data", "error"} and progress goes to
stderr. Exit codes: 0 ok, 1 failed, 2 usage, 3 not on the tailnet, 4 not in a
checkout, 5 missing dependency. No command prompts; interactive=true in the
catalog marks the ones that open a browser or a shell.
"""


def catalog_entry(path: list[str], parser: argparse.ArgumentParser, aliases: list[str]) -> dict:
    meta: Meta = parser._defaults['meta']
    arguments = []
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction) or action.dest == 'json':
            continue
        arguments.append({
            'name': action.dest,
            'flags': list(action.option_strings),
            'positional': not action.option_strings,
            'required': bool(action.required) if action.option_strings else action.nargs not in ('?', '*', '...'),
            'repeatable': isinstance(action, (argparse._AppendAction, argparse._ExtendAction)),
            'takes_value': action.nargs != 0,
            'choices': list(action.choices) if action.choices else None,
            'default': action.default if action.default not in (None, argparse.SUPPRESS, False) else None,
            'help': action.help,
        })
    return {'command': ' '.join(path), 'aliases': aliases, **meta.as_dict(), 'arguments': arguments}


def walk(parser: argparse.ArgumentParser, path: list[str]):
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        seen: dict[int, tuple[str, list[str]]] = {}
        for name, sub in action.choices.items():
            if id(sub) in seen:
                seen[id(sub)][1].append(name)
            else:
                seen[id(sub)] = (name, [])
        for sub_id, (name, aliases) in seen.items():
            sub = next(p for p in action.choices.values() if id(p) == sub_id)
            if 'meta' in sub._defaults:
                yield catalog_entry([*path, name], sub, aliases)
            yield from walk(sub, [*path, name])


def catalog(parser) -> list[dict]:
    return list(walk(parser, []))


def commands_command(ctx: Context) -> Result:
    entries = [entry for entry in catalog(ctx.args.parser)
               if not ctx.args.prefix or entry['command'].startswith(' '.join(ctx.args.prefix))]
    if ctx.args.prefix and not entries:
        raise UsageError(f"no command starts with {' '.join(ctx.args.prefix)}", hint='run `gradctl commands`')
    width = max(len(entry['command']) for entry in entries)
    lines = []
    for entry in entries:
        flags = ''.join(f' [{flag}]' for flag, on in (('net', entry['network']), ('repo', entry['repo']),
                                                      ('interactive', entry['interactive'])) if on)
        lines.append(f"{entry['command']:{width}}  {entry['effects']:11}  {entry['summary']}{flags}")
    data = {
        'version': VERSION,
        'tailnet': {'required': True, 'name': tailnet.TAILNET,
                    'exempt': [e['command'] for e in entries if not e['tailnet']],
                    'github_actions': 'commands with network=false run in GitHub Actions without the tailnet'},
        'output': 'with --json, stdout is one envelope {ok, command, data, error{code,message,hint}}',
        'exit_codes': {str(code): meaning for code, meaning in EXIT_CODES.items()},
        'commands': entries,
    }
    return Result(data=data, text='\n'.join(lines))


def version_command(ctx: Context) -> Result:
    data = {'version': VERSION, 'build': BUILD, 'python': sys.version.split()[0],
            'source': os.path.dirname(os.path.abspath(__file__))}
    return Result(data=data, text=f"gradctl {VERSION}{' (' + BUILD + ')' if BUILD else ''}")


def build_parser() -> Parser:
    common = Parser(add_help=False)
    common.add_argument('--json', action='store_true', default=argparse.SUPPRESS,
                        help='print one JSON envelope on stdout (also GRADCTL_JSON=1)')
    parser = Parser(prog='gradctl', description=__doc__, epilog=EPILOG,
                    formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--json', action='store_true', default=False,
                        help='print one JSON envelope on stdout (also GRADCTL_JSON=1)')
    parser.add_argument('--version', action='version', version=f'gradctl {VERSION}')
    commands = parser.add_subparsers(dest='command', metavar='COMMAND')

    sub = leaf(commands, 'commands', commands_command, Meta(
        'List every command with its arguments, effects and requirements', network=False, tailnet=False), common)
    sub.add_argument('prefix', nargs='*', help='only commands under this path, for example `compute`')
    sub.set_defaults(parser=parser)
    leaf(commands, 'version', version_command, Meta('Print the gradctl version', network=False, tailnet=False),
         common)
    tailnet.register(commands, common)
    devex.register(commands, common)
    envfile.register(commands, common)
    compute.register(commands, common)
    repos.register(commands, common)
    gpu = repotools.group(commands, 'gpu', repotools.GROUPS['gpu'])
    lease.register(gpu, common)
    repotools.register(commands, common, {'gpu': gpu})
    return parser


def env_json() -> bool:
    return os.environ.get('GRADCTL_JSON', '').lower() in ('1', 'true', 'yes')


def wants_json(argv: list[str]) -> bool:
    """Best guess before parsing, for reporting a usage error."""
    before = argv[:argv.index('--')] if '--' in argv else argv
    return '--json' in before or env_json()


def report_error(command: str, error: CliError, as_json: bool) -> int:
    if as_json:
        emit_json(error_envelope(command, error))
    else:
        print(f'gradctl: {error.message}', file=sys.stderr)
        if error.hint:
            print(f'hint: {error.hint}', file=sys.stderr)
    return error.exit_code


def report(command: str, result: Result, as_json: bool) -> int:
    if as_json:
        emit_json(envelope(command, result))
    else:
        if result.text:
            print(result.text)
        elif result.text is None and result.data is not None:
            import json
            print(json.dumps(result.data, indent=1, default=str))
        if not result.ok:
            print(f"gradctl: {result.error or 'failed'}", file=sys.stderr)
    return result.exit_code if not result.ok else 0


def run(argv: list[str]) -> int:
    as_json = wants_json(argv)
    command = 'gradctl'
    try:
        parser = build_parser()
        try:
            args, extra = parser.parse_known_args(argv)
        except SystemExit as exit_:
            # --help and --version print and exit 0.
            return exit_.code if isinstance(exit_.code, int) else 0
        # Decided from what argparse parsed, so a --json inside `compute ssh`'s remote command does not count.
        as_json = bool(getattr(args, 'json', False)) or env_json()
        if not hasattr(args, 'run'):
            target = getattr(args, 'group_parser', parser)
            if not as_json:
                target.print_help(sys.stderr)
            raise UsageError('choose a command', hint=f'run `{target.prog} --help` or `gradctl commands`')
        command = args.command_path
        meta: Meta = args.meta
        if extra and extra[0] == '--':
            extra = extra[1:]
        if extra and not meta.forwards_args:
            raise UsageError(f"unrecognized arguments: {' '.join(extra)}", hint=f'run `gradctl {command} --help`')
        args.forwarded = extra
        if tailnet.needed(meta):
            tailnet.require()
        ctx = Context(args=args, command=command, json=as_json)
        try:
            if as_json:
                with stdout_to_stderr():
                    result = args.run(ctx)
            else:
                result = args.run(ctx)
        except SystemExit as exit_:
            error = system_exit_error(exit_)
            if error:
                raise error from None
            result = None
        except subprocess.CalledProcessError as failed:
            raise CliError(f"{' '.join(map(str, failed.cmd[:3]))} exited with status {failed.returncode}") from None
        return report(command, result or Result(), as_json)
    except CliError as error:
        return report_error(command, error, as_json)
    except KeyboardInterrupt:
        return report_error(command, CliError('interrupted', 'interrupted', exit_code=130), as_json)
    except Exception as error:  # noqa: BLE001 - every failure gets an envelope
        if os.environ.get('GRADCTL_DEBUG'):
            traceback.print_exc()
        return report_error(command, CliError(f'{type(error).__name__}: {error}', 'internal',
                                              'rerun with GRADCTL_DEBUG=1 for a traceback'), as_json)


def main(argv: list[str] | None = None) -> None:
    if sys.version_info < (3, 10):
        raise SystemExit('gradctl needs Python 3.10 or newer')
    raise SystemExit(run(list(sys.argv[1:] if argv is None else argv)))
