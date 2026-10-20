"""Exercise the actual trusted workflow script with offline GitHub API fixtures."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
HEAD = "a" * 40
OLD = "b" * 40
FOREIGN = "c" * 40


@unittest.skipUnless(shutil.which("jq"), "workflow script requires jq")
class ReviewGateTests(unittest.TestCase):
    def run_gate(self, codex=None, graphite=None, codex_state="completed", state="open"):
        workflow = (ROOT / ".github/workflows/ai-review-gate.yml").read_text()
        script = textwrap.dedent(workflow.split("        run: |\n", 1)[1])
        fixture = {"head": HEAD, "old": OLD, "codex": codex,
                   "graphite": graphite, "codex_state": codex_state, "state": state}
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "fixture.json").write_text(json.dumps(fixture))
            gh = directory / "gh"
            gh.write_text(textwrap.dedent('''\
                #!/usr/bin/env python3
                import json, os, pathlib, sys
                f=json.loads(pathlib.Path('fixture.json').read_text())
                args=sys.argv[1:]
                endpoint=next(x for x in args if x=='graphql' or x.startswith('repos/'))
                if '/statuses/' in endpoint:
                    fields=dict(x.split('=',1) for x in args if '=' in x)
                    pathlib.Path('status.json').write_text(json.dumps(fields))
                    print('{}')
                elif endpoint.endswith('/commits'):
                    print(f['old']); print(f['head'])
                elif endpoint.endswith('/reviews'):
                    pass
                elif endpoint=='graphql':
                    rows=[]
                    if f['codex']:
                        marker={'code_review':{'status':f['codex_state'],'commit_sha':f['codex']}}
                        rows=[{'body':'<!-- codex-review-state:v1 '+json.dumps(marker)+' -->',
                               'userContentEdits':{'nodes':[]}}]
                    print(json.dumps(rows))
                elif '/check-runs?' in endpoint:
                    sha=endpoint.split('/commits/')[1].split('/')[0]
                    rows=[]
                    g=f['graphite']
                    if g and sha==g[0]:
                        rows=[{'status':'completed','conclusion':g[1],
                               'started_at':'2026-10-20T00:00:00Z'}]
                    print(json.dumps(rows))
                elif '/pulls/' in endpoint:
                    print(json.dumps({'state':f['state'],'head':{'sha':f['head']}}))
                else:
                    raise SystemExit('Unexpected API operation: '+endpoint)
                '''))
            gh.chmod(0o755)
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ["PATH"],
                       REPO="Gradiated/gradiated", PR="714", RUN_URL="https://example.test/run")
            result = subprocess.run(["bash", "-c", script], cwd=tmp, env=env,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            status = directory / "status.json"
            return json.loads(status.read_text()) if status.exists() else None

    def test_codex_only_passes(self):
        result = self.run_gate(codex=HEAD)
        self.assertEqual(result["state"], "success")
        self.assertIn("Codex reviewed", result["description"])

    def test_graphite_only_passes_even_when_codex_failed(self):
        result = self.run_gate(codex=HEAD, codex_state="failed", graphite=(HEAD, "success"))
        self.assertEqual(result["state"], "success")
        self.assertIn("Graphite reviewed", result["description"])

    def test_both_pass(self):
        self.assertEqual(self.run_gate(codex=HEAD, graphite=(HEAD, "success"))["state"], "success")

    def test_neither_stays_pending(self):
        self.assertEqual(self.run_gate()["state"], "pending")

    def test_running_failed_and_skipped_do_not_count(self):
        for state in ("running", "failed"):
            with self.subTest(state=state):
                self.assertEqual(self.run_gate(codex=HEAD, codex_state=state,
                                               graphite=(HEAD, "skipped"))["state"], "pending")

    def test_foreign_commit_does_not_count(self):
        self.assertEqual(self.run_gate(codex=FOREIGN, graphite=(FOREIGN, "success"))["state"], "pending")

    def test_earlier_pr_commit_still_counts(self):
        self.assertEqual(self.run_gate(codex=OLD)["state"], "success")
        self.assertEqual(self.run_gate(graphite=(OLD, "success"))["state"], "success")

    def test_closed_pr_does_not_write_status(self):
        self.assertIsNone(self.run_gate(codex=HEAD, state="closed"))


if __name__ == "__main__":
    unittest.main()
