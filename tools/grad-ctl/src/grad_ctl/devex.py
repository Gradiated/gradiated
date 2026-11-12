"""Repository DevEx: the startup context pack, environment report and dependency-free checks."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import VERSION, tailnet
from .core import Context, Meta, Result, group, leaf

NAME_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')

WORKSTREAMS = {
    'sol': {
        'instructions': 'research/lab/AGENTS.md',
        'start': 'research/lab/README.md',
        'checks': 'cd research/lab && cargo fmt --check && cargo clippy --workspace --all-targets -- -D warnings '
                  '&& cargo test --workspace',
    },
}
READ_FIRST = ('AGENTS.md', 'README.md', 'docs/ARCHITECTURE.md', 'docs/DATA_MODEL.md')
REPO_PATHS = ('AGENTS.md', 'README.md', 'docs/DATA_MODEL.md', 'docs/ARCHITECTURE.md', 'research/README.md',
              '.agents/skills', 'tools/grad-ctl', 'tools/browser/pyproject.toml', 'research/lab')
COMMANDS = ('git', 'docker', 'uv', 'cargo', 'rustc', 'gh', 'node', 'mise', 'aws', 'kubectl', 'tailscale', 'nebius')
BROWSER_MODULES = ('playwright', 'browser_use', 'pytest')
CREDENTIAL_TOKENS = ('API_KEY', 'TOKEN', 'SECRET', 'PASSWORD')


# Skills

def frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        raise ValueError('missing opening frontmatter')
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == '---')
    except StopIteration as exc:
        raise ValueError('missing closing frontmatter') from exc
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if ':' not in line:
            raise ValueError(f'invalid frontmatter line: {line!r}')
        key, value = line.split(':', 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def validate_skill(path: Path) -> list[str]:
    errors: list[str] = []
    name = path.parent.name
    if not NAME_RE.fullmatch(name):
        errors.append(f'invalid directory name {name!r}')
    try:
        metadata = frontmatter(path.read_text())
    except (OSError, ValueError) as exc:
        return [f'{path}: {exc}']
    if metadata.get('name') != name:
        errors.append(f'frontmatter name must be {name!r}')
    if not metadata.get('description'):
        errors.append('frontmatter description is empty')
    ui = path.parent / 'agents' / 'openai.yaml'
    if not ui.is_file():
        errors.append('missing agents/openai.yaml')
    else:
        ui_text = ui.read_text()
        for field in ('display_name', 'short_description', 'default_prompt'):
            if f'  {field}:' not in ui_text:
                errors.append(f'openai.yaml missing interface.{field}')
        if f'$${name}' in ui_text or f'${name}' not in ui_text:
            errors.append(f'openai.yaml default_prompt must mention ${name}')
    return [f'{path}: {error}' for error in errors]


def skills_report(root: Path) -> dict:
    skills = sorted((root / '.agents' / 'skills').glob('*/SKILL.md'))
    errors = [error for path in skills for error in validate_skill(path)]
    if not skills:
        errors = [f"no skills found under {root / '.agents' / 'skills'}"]
    return {'ok': not errors, 'validated': len(skills), 'errors': errors}


def skills_text(report: dict) -> str:
    return '\n'.join(report['errors']) if report['errors'] else f"validated {report['validated']} repo-local skills"


def skills(ctx: Context) -> Result:
    report = skills_report(ctx.repo())
    return Result(data=report, text=skills_text(report), ok=report['ok'], exit_code=0 if report['ok'] else 1,
                  error=None if report['ok'] else f"{len(report['errors'])} skill errors",
                  error_code='check_failed')


# Doctor

def browser_module(root: Path, name: str) -> str:
    import importlib.util
    if importlib.util.find_spec(name):
        return 'ok'
    if shutil.which('uv') is None:
        return 'missing'
    result = subprocess.run(['uv', 'run', '--project', 'tools/browser', 'python', '-c', f'import {name}'],
                            cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return 'ok (tools/browser)' if result.returncode == 0 else 'missing'


def doctor_report(root: Path) -> dict:
    return {
        'repo': str(root),
        'grad_ctl': VERSION,
        'python': sys.executable,
        'tailnet': tailnet.check(),
        'commands': {name: shutil.which(name) for name in COMMANDS},
        'python_modules': {name: browser_module(root, name) for name in BROWSER_MODULES},
        'repo_paths': {path: (root / path).exists() for path in REPO_PATHS},
        # Names only: values never leave the environment.
        'credential_variables': sorted(name for name in os.environ if any(t in name for t in CREDENTIAL_TOKENS)),
    }


def doctor_text(report: dict) -> str:
    net = report['tailnet']
    lines = [f"repo: {report['repo']}", f"grad-ctl: {report['grad_ctl']}", f"python: {report['python']}",
             f"tailnet: {'connected as ' + str(net.get('dns_name')) if net['connected'] else net['reason']}",
             '', 'Commands:']
    lines += [f"  {name:10} {'ok (' + path + ')' if path else 'missing'}" for name, path in report['commands'].items()]
    lines += ['', 'Python modules:']
    lines += [f'  {name:16} {state}' for name, state in report['python_modules'].items()]
    lines += ['', 'Repo paths:']
    lines += [f"  {path:32} {'present' if ok else 'missing'}" for path, ok in report['repo_paths'].items()]
    lines += ['', 'Credential variables present (values hidden):',
              '  ' + (', '.join(report['credential_variables']) or 'none')]
    return '\n'.join(lines)


def doctor(ctx: Context) -> Result:
    report = doctor_report(ctx.repo())
    return Result(data=report, text=doctor_text(report))


# Context pack

def git_summary(root: Path) -> dict:
    result = subprocess.run(['git', 'status', '--short', '--branch'], cwd=root, text=True, capture_output=True,
                            check=False)
    lines = result.stdout.splitlines()
    return {'branch': lines[0] if lines else 'git status unavailable',
            'changed': sum(1 for line in lines[1:] if line.strip())}


def context_report(root: Path, workstream: str | None) -> dict:
    selected = [workstream] if workstream else list(WORKSTREAMS)
    return {
        'repo': str(root),
        'git': git_summary(root),
        'read_first': {path: (root / path).exists() for path in READ_FIRST},
        'workstreams': {name: {**{key: {'path': WORKSTREAMS[name][key],
                                        'present': (root / WORKSTREAMS[name][key]).exists()}
                                  for key in ('instructions', 'start')},
                               'checks': WORKSTREAMS[name]['checks']} for name in selected},
        'before_changing_files': [
            'inspect git status and preserve unrelated worktree changes',
            "reserve directory/artifact scope; do not edit another agent's files",
            'state the acceptance check and any test budget or timeout',
        ],
        'cli': 'run `grad-ctl commands --json` for every command, its effects and requirements',
    }


def context_text(report: dict) -> str:
    git = report['git']
    state = lambda ok: 'present' if ok else 'missing'  # noqa: E731
    lines = ['AGENT CONTEXT PACK', f"repo: {report['repo']}",
             f"git: {git['branch']} ({git['changed']} changed/untracked entries; inspect before editing)",
             '', 'Read first:']
    lines += [f'- {path} [{state(ok)}]' for path, ok in report['read_first'].items()]
    for name, spec in report['workstreams'].items():
        lines += ['', f'Workstream: {name}']
        lines += [f"- {spec[key]['path']} [{state(spec[key]['present'])}]" for key in ('instructions', 'start')]
        lines.append(f"- checks: {spec['checks']}")
    lines += ['', 'Before changing files:', *(f'- {item}' for item in report['before_changing_files'])]
    lines += ['', f"CLI: {report['cli']}"]
    return '\n'.join(lines)


def context(ctx: Context) -> Result:
    report = context_report(ctx.repo(), ctx.args.workstream)
    return Result(data=report, text=context_text(report))


# Check and start

def check_report(root: Path) -> dict:
    report = skills_report(root)
    checks = [{'name': 'skills', **report}, {'name': 'doctor', 'ok': True, **doctor_report(root)}]
    return {'ok': all(item['ok'] for item in checks), 'checks': checks}


def check_text(report: dict) -> str:
    skills_check, doctor_check = report['checks']
    return skills_text(skills_check) + '\n' + doctor_text(doctor_check)


def check(ctx: Context) -> Result:
    report = check_report(ctx.repo())
    return Result(data=report, text=check_text(report), ok=report['ok'], exit_code=0 if report['ok'] else 1,
                  error=None if report['ok'] else 'DevEx checks failed', error_code='check_failed')


def start(ctx: Context) -> Result:
    root = ctx.repo()
    pack = context_report(root, ctx.args.workstream)
    report = check_report(root)
    text = context_text(pack) + '\n' + check_text(report)
    if report['ok']:
        text += '\nagent startup checks passed'
    return Result(data={'context': pack, 'check': report}, text=text, ok=report['ok'],
                  exit_code=0 if report['ok'] else 1, error=None if report['ok'] else 'DevEx checks failed',
                  error_code='check_failed')


def register(commands, common) -> None:
    sub = group(commands, 'devex', 'Repository DevEx: startup context and the dependency-free checks')
    local = dict(network=False, repo=True)
    for name, run, summary in (
        ('start', start, 'Print the context pack and run the DevEx checks: the first command of every agent turn'),
        ('context', context, 'Print the compact, deterministic context pack for a new agent'),
    ):
        leaf(sub, name, run, Meta(summary, **local), common).add_argument('--workstream', choices=sorted(WORKSTREAMS))
    leaf(sub, 'check', check, Meta('Run the dependency-free DevEx checks (skills, environment)', **local), common)
    leaf(sub, 'doctor', doctor, Meta('Report tools, paths, tailnet and credential names (never values)', **local),
         common)
    leaf(sub, 'skills', skills, Meta('Validate the repo-local agent skills in .agents/skills', **local), common)
