"""Repository tools gradctl runs from the checkout.

These render or edit files in the repository, and CI runs some of them by path,
so their code stays beside what they change. gradctl is their one entry point
for people and agents: it finds the checkout, applies the tailnet requirement
and wraps the result in the --json envelope. Arguments after the command name
are passed through unchanged; `gradctl gpu render-config -- --help` shows the
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
    # Binaries the script itself runs, beyond the ones that launch it.
    requires: tuple[str, ...] = ()
    # Binaries the script finds on PATH unless a flag names one: (binary, flag).
    requires_unless: tuple[tuple[str, str], ...] = ()


def python(path: str) -> tuple[str, ...]:
    return ('{python}', path)


# uv installs the locked environment on first use, so these commands are networked.
BROWSER = ('uv', 'run', '--locked', '--project', 'tools/browser', 'python')

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
    Tool('gpu', 'prepare-enrollment', (python('tools/gpu/prepare-enrollment.py'),),
         'Prepare idle bootstrap enrollment in place over admin Tailscale SSH',
         requires=('git', 'tailscale')),
    Tool('gpu', 'mint-bootstrap-key', (python('tools/gpu/mint-bootstrap-key.py'),),
         'Mint the single-use Tailscale key a new or re-imaged GPU pod uses on first start',
         requires=('aws',)),
    Tool('gpu', 'create-runpod-template', (python('tools/gpu/create-runpod-template.py'),),
         'Create one private RunPod template from the repository catalog, without allocating GPUs'),
    Tool('gpu', 'qualification-slot', (python('tools/gpu/qualification-slot.py'),),
         'Reserve spare node capacity for isolated GPU qualification without draining pods',
         requires=('kubectl',)),
    Tool('github-apps', 'create', (('node', 'tools/github-apps/create.mjs'),),
         'Create Gradiated GitHub Apps and store their keys without printing them (opens a browser)',
         interactive=True,
         requires=('aws', 'gh')),
    Tool('browser', 'sync', (('uv', 'sync', '--project', 'tools/browser'),),
         'Install the browser automation environment in tools/browser'),
    Tool('browser', 'install', (('uv', 'run', '--project', 'tools/browser', 'playwright', 'install', 'chromium'),),
         'Install the Chromium build Playwright uses'),
    Tool('lab', 'check', (('cargo', 'fmt', '--manifest-path', 'research/lab/Cargo.toml', '--all', '--', '--check'),
                          ('cargo', 'test', '--manifest-path', 'research/lab/Cargo.toml', '--workspace')),
         'Check formatting and run the tests of the research lab workspace', effects='read', network=False),

    # Security and compliance.
    Tool('security', 'argocd-auth', (python('tools/security/check_argocd_auth.py'),),
         'Exercise the pinned Argo CD login gate with signed, synthetic OIDC identities', effects='read',
         requires=('docker',)),
    Tool('security', 'temporal-ui', (python('tools/security/check_temporal_ui.py'),),
         'Validate the pinned Temporal UI and OAuth proxy offline with fixture credentials (needs Docker)',
         effects='read', requires=('docker',)),
    Tool('security', 'audit-controls', (python('tools/security/validate_audit_controls.py'),),
         'Validate rendered audit policies and event patterns with read-only AWS APIs; sends no events',
         effects='read', requires=('aws',)),
    Tool('security', 'unauthorized-calls', (python('tools/security/validate_unauthorized_calls.py'),),
         "Test the rendered unauthorized-call filter with AWS's read-only filter engine", effects='read',
         requires=('aws',)),
    Tool('security', 'ci-boundaries', (python('tools/security/simulate_ci_boundaries.py'),),
         'Simulate the CI IAM boundaries rendered by `terraform test -json -verbose`, read-only', effects='read',
         requires=('aws',)),

    # Observability checks over the rendered monitoring configuration.
    Tool('observability', 'check', (python('tools/observability/check.py'),),
         'Check alert and dashboard links, PromQL, and probe and stall behaviour (--promtool PATH)',
         effects='read', network=False,
         requires_unless=(('promtool', '--promtool'),)),
    Tool('observability', 'platform', (python('tools/observability/check_platform.py'),),
         'Render the pinned monitoring chart and exercise its incident routing (--amtool, --alertmanager)',
         effects='read', requires=('helm',),
         requires_unless=(('amtool', '--amtool'), ('alertmanager', '--alertmanager'))),
    Tool('observability', 'controller-requests', (python('tools/observability/check_controller_requests.py'),),
         'Render the pinned controller charts and require their scheduler reservations', effects='read',
         requires=('helm',)),

    # Production model operations.
    Tool('models', 'monitoring-billing', (('node', 'tools/models/monitoring-billing.mjs'),),
         'Preview the internal monitoring billing reserve; --apply-credit posts the approved credit',
         requires=('kubectl',)),
    Tool('models', 'probe-readiness', (('node', 'tools/deployment/inference-probe-readiness.mjs'),),
         'Check every deployment has fresh successful inference probes', effects='read', requires=('kubectl',)),

    # Browser automation.
    Tool('browser', 'website-screenshots', (BROWSER + ('tools/browser/website_screenshots.py',),),
         'Capture the built website pages and interactions for PR image diffs'),
    Tool('browser', 'storybook-screenshots', (BROWSER + ('tools/browser/storybook_screenshots.py',),),
         'Capture every built console story as a PNG (--story-prefix, --output)'),
    Tool('browser', 'temporal-ui', (BROWSER + ('tools/browser/check_temporal_ui.py',),),
         'Render the production Temporal Cloud frontend against a synthetic namespace reader (IMAGE)',
         effects='read', requires=('docker',)),

    # Local product development.
    Tool('product', 'sglang-local', (('bash', 'product/scripts/run-sglang-local.sh'),),
         'Run the pinned Apple Silicon SGLang development model; the first run fetches SGLang and the model',
         effects='read', interactive=True, requires=('git', 'uv', 'xcrun')),
    Tool('product', 'temporal-ui-local', (('bash', 'product/scripts/run-temporal-ui-local.sh'),),
         'Run the Temporal UI locally against the development Temporal server; the first run downloads it',
         effects='read', interactive=True, requires=('curl', 'tar')),
    Tool('product', 'opencode', (('bash', 'product/scripts/opencode-gradiated.sh'),),
         'Run opencode against Gradiated inference; the session can edit files and run commands', interactive=True,
         requires=('aws', 'jq', 'opencode')),
    Tool('product', 'desmond-build-image', (('bash', 'product/scripts/desmond-build-image.sh'),),
         'Build the desmond SGLang image locally (DESMOND_IMAGE, default gradiated/desmond-sglang:dev)',
         requires=('docker', 'git')),
    Tool('product', 'desmond-test', (('bash', 'product/scripts/desmond-test.sh'),),
         'Build desmondd and run its native tests with CMake', effects='read', network=False,
         requires=('cmake', 'git')),

    # Agent skills.
    Tool('research', 'decision-data', (python('tools/decision_training/prepare.py'),),
         'Build a pinned, screened public decision-training mixture and frozen JevBench evaluation'),
    Tool('research', 'decision-data-scale', (python('tools/decision_training/prepare_scale.py'),),
         'Normalize verified public scale-up candidate shards; separate admission is required', network=False),
    Tool('research', 'decision-data-audit', (python('tools/decision_training/audit_scale.py'),),
         'Audit exact candidate conflicts and protected benchmark case components; does not admit training', network=False),
    Tool('research', 'decision-token-audit', (python('tools/decision_training/audit_tokens.py'),),
         'Measure exact native Inkling candidate token lengths with hash-verified tokenizer files', network=False),
    Tool('research', 'decision-semantic-audit', (python('tools/decision_training/audit_semantics.py'),),
         'Check supported procedural targets with independent Bayesian, incident and route oracles', network=False),
    Tool('research', 'decision-release-index', (python('tools/decision_training/release_index.py'),),
         'Apply source policy and prompt repairs, then index protected/duplicate groups and source-family holdouts', network=False),
    Tool('research', 'decision-release-export', (python('tools/decision_training/release_export.py'),),
         'Export a verified source-balanced decision release with grouped dev and exact token caches', network=False),
    Tool('research', 'decision-release-verify', (python('tools/decision_training/cached_data.py'),),
         'Verify reviewed release builders, native runtime and optional checkpoint/baseline payloads without modifying them', network=False),
    Tool('research', 'decision-adapter-restore-smoke', (python('tools/decision_training/adapter_restore.py'),),
         'Check bitwise LoRA restoration and gradients for a real PEFT weight_proj module on CPU', network=False),
    Tool('research', 'decision-repair-resume', (python('tools/decision_training/repair_resume.py'),),
         'Derive an audited loader-compatible checkpoint for the measured PEFT weight_proj restore bug; preserve origin bytes', network=False),
    Tool('research', 'decision-train', (python('tools/decision_training/train.py'),),
         'Fine-tune Inkling decision adapters, checkpoint to scoped S3 and evaluate public JevBench'),
    Tool('research', 'decision-distributed-smoke', (python('tools/decision_training/smoke_distributed.py'),),
         'Check torchrun accumulation and optimizer/RNG resume against a full-batch toy oracle', network=False),
    Tool('research', 'decision-compare', (python('tools/decision_training/compare.py'),),
         'Compare frozen decision predictions with fair dev calibration and paired uncertainty', network=False),
    Tool('research', 'decision-probe', (python('tools/decision_training/probe.py'),),
         'Diagnose padding and numerical batch sensitivity of the released Inkling implementation'),
    Tool('research', 'decision-checkpoint-eval', (python('tools/decision_training/checkpoint_eval.py'),),
         'Compare one hash-verified adapter with untouched Inkling using singleton inference only', network=False),
    Tool('research', 'efficiency', (python('.agents/skills/experiment-run/scripts/research_efficiency.py'),),
         'Account Codex and provider throughput for $experiment-run from event timing, not reasoning text',
         network=False),
)
GROUPS = {
    'gpu': 'GPU fleet: host leases and the repository tools that render, pin and stage the fleet',
    'github-apps': 'Gradiated GitHub Apps',
    'browser': 'Browser automation environment for $browser-research',
    'lab': 'The research lab Rust workspace',
    'infra': 'Credential-free infrastructure formatting and checks',
    'security': 'Security and compliance checks',
    'observability': 'Checks over the rendered monitoring configuration',
    'models': 'Production model operations',
    'product': 'Local product development',
    'research': 'Research tooling for the agent skills',
}


def runner(tool: Tool):
    def run(ctx: Context) -> Result:
        root = ctx.repo()
        steps = [[sys.executable if part == '{python}' else part for part in step] for step in tool.steps]
        # Extra arguments go to the last step, the tool itself.
        steps[-1] += ctx.args.forwarded
        given = ctx.args.forwarded
        located = [binary for binary, flag in tool.requires_unless
                   if not any(arg == flag or arg.startswith(flag + '=') for arg in given)]
        for binary in (*(step[0] for step in steps), *tool.requires, *located):
            if not shutil.which(binary):
                raise DependencyMissing(binary)
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
                # Exit 1: the tool's own code could collide with gradctl's (2 usage, 3 tailnet, ...).
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
                    requires=tuple(dict.fromkeys((*(step[0] for step in tool.steps if step[0] != '{python}'),
                                                  *tool.requires,
                                                  *(binary for binary, _ in tool.requires_unless)))))
        leaf(groups[tool.group], tool.name, runner(tool), meta, common,
             epilog='Arguments after the command go to the tool; use `-- --help` for its own help.')
