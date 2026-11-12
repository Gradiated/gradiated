"""Repository tools grad-ctl runs from the checkout.

These render or edit files in the repository, and CI runs some of them by path,
so their code stays beside what they change. grad-ctl is their one entry point
for people and agents: it finds the checkout, applies the tailnet requirement
and wraps the result in the --json envelope. Arguments after the command name
are passed through unchanged; `grad-ctl gpu render-config -- --help` shows the
tool's own help.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

from .core import Context, DependencyMissing, Meta, Result, group, leaf


@dataclass(frozen=True)
class Tool:
    group: str
    name: str
    steps: tuple[tuple[str, ...], ...]
    summary: str
    effects: str = 'write'
    network: bool = True
    interactive: bool = False


def python(path: str) -> tuple[str, ...]:
    return ('{python}', path)


TOOLS = (
    Tool('gpu', 'render-config', (python('tools/gpu/render-config.py'),),
         'Render GPU controller inventory and model Rollouts from hosts.yaml and models.json (--check verifies)',
         network=False),
    Tool('gpu', 'stage-glm-pool', (python('tools/gpu/stage-glm-pool.py'),),
         'Stage an isolated non-B300 uncensored GLM pool, then promote it', network=False),
    Tool('gpu', 'stage-kimi-pool', (python('tools/gpu/stage-kimi-pool.py'),),
         'Stage qualified Kimi on its reserved 8xB300 hosts', network=False),
    Tool('gpu', 'pin-host', (python('tools/gpu/pin-host.py'),),
         'Pin a published host bundle and render the fleet configuration', network=False),
    Tool('gpu', 'pin-sglang-pools', (python('tools/gpu/pin-sglang-pools.py'),),
         'Pin the GLM and DeepSeek SGLang pools to their published bundles', network=False),
    Tool('gpu', 'prepare-enrollment', (python('tools/gpu/prepare-enrollment.py'),),
         'Prepare idle bootstrap enrollment in place over admin Tailscale SSH'),
    Tool('gpu', 'mint-bootstrap-key', (python('tools/gpu/mint-bootstrap-key.py'),),
         'Mint the single-use Tailscale key a new or re-imaged GPU pod uses on first start'),
    Tool('gpu', 'create-runpod-template', (python('tools/gpu/create-runpod-template.py'),),
         'Create one private RunPod template from the repository catalog, without allocating GPUs'),
    Tool('gpu', 'qualification-slot', (python('tools/gpu/qualification-slot.py'),),
         'Reserve spare node capacity for isolated GPU qualification without draining pods'),
    Tool('github-apps', 'create', (('node', 'tools/github-apps/create.mjs'),),
         'Create Gradiated GitHub Apps and store their keys without printing them (opens a browser)',
         interactive=True),
    Tool('browser', 'sync', (('uv', 'sync', '--project', 'tools/browser'),),
         'Install the browser automation environment in tools/browser'),
    Tool('browser', 'install', (('uv', 'run', '--project', 'tools/browser', 'playwright', 'install', 'chromium'),),
         'Install the Chromium build Playwright uses'),
    Tool('lab', 'check', (('cargo', 'fmt', '--manifest-path', 'research/lab/Cargo.toml', '--all', '--', '--check'),
                          ('cargo', 'test', '--manifest-path', 'research/lab/Cargo.toml', '--workspace')),
         'Check formatting and run the tests of the research lab workspace', effects='read', network=False),
)
GROUPS = {
    'gpu': 'GPU fleet: host leases and the repository tools that render, pin and stage the fleet',
    'github-apps': 'Gradiated GitHub Apps',
    'browser': 'Browser automation environment for $browser-research',
    'lab': 'The research lab Rust workspace',
}


def runner(tool: Tool):
    def run(ctx: Context) -> Result:
        root = ctx.repo()
        steps = [[sys.executable if part == '{python}' else part for part in step] for step in tool.steps]
        # Extra arguments go to the last step, the tool itself.
        steps[-1] += ctx.args.forwarded
        for step in steps:
            if not shutil.which(step[0]):
                raise DependencyMissing(step[0])
        runs = []
        for step in steps:
            # An interactive tool shows a URL or prompt as it runs; under --json its stdout is stderr.
            if ctx.json and not tool.interactive:
                result = subprocess.run(step, cwd=root, capture_output=True, text=True)
                runs.append({'argv': step, 'exit_code': result.returncode, 'stdout': result.stdout,
                             'stderr': result.stderr})
            else:
                result = subprocess.run(step, cwd=root)
                runs.append({'argv': step, 'exit_code': result.returncode})
            if result.returncode:
                # Exit 1: the tool's own code could collide with grad-ctl's (2 usage, 3 tailnet, ...).
                return Result(data={'steps': runs}, text='', ok=False, exit_code=1,
                              error=f'{tool.group} {tool.name}: {step[1] if step[0] == sys.executable else step[0]} '
                                    f'exited with status {result.returncode}')
        # The tool printed its own output; --json carries it in data.
        return Result(data={'steps': runs}, text='')
    return run


def register(commands, common, groups: dict) -> None:
    """Add every tool, creating its group unless the caller already made it (as gpu is)."""
    for tool in TOOLS:
        if tool.group not in groups:
            groups[tool.group] = group(commands, tool.group, GROUPS[tool.group])
        meta = Meta(tool.summary, effects=tool.effects, network=tool.network, repo=True, forwards_args=True,
                    interactive=tool.interactive,
                    requires=tuple(dict.fromkeys(step[0] for step in tool.steps if step[0] != '{python}')))
        leaf(groups[tool.group], tool.name, runner(tool), meta, common,
             epilog='Arguments after the command go to the tool; use `-- --help` for its own help.')
