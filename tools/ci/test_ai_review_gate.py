"""Exercise the actual trusted workflow scripts with offline GitHub API fixtures."""
import base64
import json
import os
import runpy
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
HEAD = "a" * 40
MID = "d" * 40
OLD = "b" * 40
FOREIGN = "c" * 40
P1 = "**<sub><sub>![P1 Badge](https://img.shields.io/badge/P1-orange?style=flat)</sub></sub>  Fix it**"
P2 = "**<sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub>  Tidy it**"
CODEX = "chatgpt-codex-connector"
APP = "gradiated-review"


def receipt(commit=HEAD[:10]):
    return {"author": {"__typename": "Bot", "login": CODEX},
            "body": "<!-- codex-review-receipt:v1 -->\n\n"
                    "Codex Review: Didn't find any major issues. :rocket:\n\n"
                    f"**Reviewed commit:** `{commit}`\n",
            "userContentEdits": {"pageInfo": {"hasNextPage": False}, "nodes": []}}


def step_scripts():
    """The run: blocks of the gate job, in order."""
    workflow = (ROOT / ".github/workflows/ai-review-gate.yml").read_text()
    blocks = workflow.split("\n  gate:\n", 1)[1].split("        run: |\n")[1:]
    return [textwrap.dedent(block.split("\n      - name:", 1)[0]) for block in blocks]


# Reviews are (author, state, commit, inline comment bodies[, review body]);
# bot authors get the [bot] suffix in REST like the real API.
FAKE_GH = '''\
#!/usr/bin/env python3
import json, pathlib, subprocess, sys
f=json.loads(pathlib.Path('fixture.json').read_text())
args=sys.argv[1:]
endpoint=next(x for x in args if x=='graphql' or x.startswith('repos/'))
values=[args[i+1] for i,x in enumerate(args[:-1]) if x in ('-f','-F')]
fields=dict(x.split('=',1) for x in values)
method=args[args.index('-X')+1] if '-X' in args else ('POST' if fields and endpoint!='graphql' else 'GET')

def write(kind):
    log=pathlib.Path('writes.json')
    rows=json.loads(log.read_text()) if log.exists() else []
    rows.append(dict(fields, kind=kind, endpoint=endpoint))
    log.write_text(json.dumps(rows))
    print('{}')

def emit(value):
    # REST calls: apply --jq like gh does, per page.
    if '--jq' in args:
        expr=args[args.index('--jq')+1]
        out=subprocess.run(['jq','-r',expr],input=json.dumps(value),capture_output=True,text=True,check=True)
        sys.stdout.write(out.stdout)
    else:
        print(json.dumps(value))

def login(who):
    return who if who=='joshsny' else who+'[bot]'

reviews=f['reviews']
if '/statuses/' in endpoint:
    write('status')
elif '/contents/tools/ci/codex_receipts.py?ref=' in endpoint:
    assert endpoint.endswith('?ref='+f['workflow_sha']), 'Parser source must be the trusted workflow revision'
    emit({'content': f['parser']})
elif '/collaborators/' in endpoint:
    emit({'role_name': f['role']})
elif endpoint.endswith('/reactions'):
    write('reaction')
elif endpoint.endswith('/dismissals'):
    write('dismissal')
elif endpoint.endswith('/commits'):
    print(f['old']); print(f['mid']); print(f['head'])
elif endpoint.endswith('/reviews') and method=='POST':
    write('review')
elif endpoint.endswith('/reviews'):
    emit([{'id': i, 'user': {'login': login(r[0])}, 'state': r[1], 'commit_id': r[2],
           'body': r[4] if len(r) > 4 else ''} for i, r in enumerate(reviews)])
elif '/issues/' in endpoint and endpoint.endswith('/comments') and method=='POST':
    write('comment')
elif '/issues/' in endpoint and endpoint.endswith('/comments'):
    emit([{'user': {'login': login(who)}, 'body': body} for who, body in f['issue_comments']])
elif endpoint.endswith('/comments'):
    emit([{'pull_request_review_id': i, 'user': {'login': login(r[0])}, 'in_reply_to_id': None,
           'original_commit_id': r[2], 'body': body}
          for i, r in enumerate(reviews) for body in r[3]])
elif endpoint=='graphql' and 'reviewThreads' in fields.get('query', ''):
    print(json.dumps({'totalCount': len(f['threads']), 'nodes': [
        {'isResolved': resolved, 'path': 'x.py',
         'comments': {'nodes': [{'author': {'login': who}, 'body': body, 'url': 'https://t/%d' % n}]}}
        for n, (who, body, resolved) in enumerate(f['threads'])]}))
elif endpoint=='graphql':
    rows=[]
    if f['codex']:
        marker={'code_review':{'status':f['codex_state'],'commit_sha':f['codex'],
                               'has_any_findings':f['codex_findings']}}
        rows=[{'body':'<!-- codex-review-state:v1 '+json.dumps(marker)+' -->',
               'userContentEdits':{'nodes':[]}}]
    rows.extend(f['receipts'])
    for row in rows:
        row.setdefault('author', {'__typename':'Bot','login':'chatgpt-codex-connector'})
    emit({'data': {'repository': {'pullRequest': {'comments': {'nodes': rows}}}}})
elif '/check-runs?' in endpoint:
    sha=endpoint.split('/commits/')[1].split('/')[0]
    rows=[]
    g=f['graphite']
    if g and sha==g[0]:
        rows=[{'status':'completed','conclusion':g[1],
               'started_at':'2026-10-20T00:00:00Z'}]
    print(json.dumps(rows))
elif '/pulls/' in endpoint:
    print(json.dumps({'state':f['state'],'head':{'sha':f['head']},
                      'base':{'ref':f['base']},'user':{'login':f['author']}}))
else:
    raise SystemExit('Unexpected API operation: '+endpoint)
'''


@unittest.skipUnless(shutil.which("jq"), "workflow script requires jq")
class ReviewGateTests(unittest.TestCase):
    def run_gate(self, codex=None, graphite=None, codex_state="completed", state="open",
                 codex_findings=False, threads=(), reviews=(), base="main", author="joshsny",
                 issue_comments=(), event="workflow_dispatch", commenter_type="", role="write",
                 ask_codex="", receipts=(), mid=MID):
        fixture = {"head": HEAD, "mid": mid, "old": OLD, "codex": codex, "graphite": graphite,
                   "codex_state": codex_state, "codex_findings": codex_findings,
                   "state": state, "threads": list(threads), "reviews": list(reviews),
                   "base": base, "author": author, "issue_comments": list(issue_comments),
                   "role": role, "receipts": list(receipts), "workflow_sha": "e"*40,
                   "parser": base64.b64encode((ROOT / 'tools/ci/codex_receipts.py').read_bytes()).decode()}
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "fixture.json").write_text(json.dumps(fixture))
            gh = directory / "gh"
            gh.write_text(FAKE_GH)
            gh.chmod(0o755)
            if not shutil.which("tac"):  # macOS: the runner has GNU tac
                tac = directory / "tac"
                tac.write_text("#!/bin/sh\ntail -r\n")
                tac.chmod(0o755)
            output = directory / "github_output"
            output.touch()
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ["PATH"],
                       REPO="Gradiated/gradiated", PR="714", RUN_URL="https://example.test/run",
                       STATUS_TOKEN="status-token", APP_SLUG=APP, GITHUB_OUTPUT=str(output),
                       EVENT=event, COMMENTER="someone", COMMENTER_TYPE=commenter_type,
                       COMMENT_ID="99", REQUESTED="", ASK_CODEX=ask_codex)
            env["WORKFLOW_SHA"] = fixture["workflow_sha"]
            for n, script in enumerate(step_scripts()):
                result = subprocess.run(["bash", "-c", script], cwd=tmp, env=env,
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                if n == 0:  # the requester step's outputs gate the later steps
                    outputs = dict(line.split("=", 1) for line in output.read_text().split())
                    if outputs.get("skip") == "true":
                        break
                    env["REQUESTED"] = outputs.get("requested", "")
            writes = directory / "writes.json"
            return json.loads(writes.read_text()) if writes.exists() else []

    def status(self, **kwargs):
        rows = [w for w in self.run_gate(**kwargs) if w["kind"] == "status"]
        return rows[-1] if rows else None

    def review(self, **kwargs):
        rows = [w for w in self.run_gate(**kwargs) if w["kind"] == "review"]
        return rows[-1] if rows else None

    def approval(self, **kwargs):
        review = self.review(**kwargs)
        return review if review and review["event"] == "APPROVE" else None

    # "AI review passed" status: unchanged rule, either reviewer.

    def test_codex_only_passes(self):
        result = self.status(codex=HEAD)
        self.assertEqual(result["state"], "success")
        self.assertIn("Codex reviewed", result["description"])

    def test_graphite_only_passes_even_when_codex_failed(self):
        result = self.status(codex=HEAD, codex_state="failed", graphite=(HEAD, "success"))
        self.assertEqual(result["state"], "success")
        self.assertIn("Graphite reviewed", result["description"])

    def test_both_pass(self):
        self.assertEqual(self.status(codex=HEAD, graphite=(HEAD, "success"))["state"], "success")

    def test_neither_stays_pending(self):
        self.assertEqual(self.status()["state"], "pending")

    def test_running_failed_and_skipped_do_not_count(self):
        for state in ("running", "failed"):
            with self.subTest(state=state):
                self.assertEqual(self.status(codex=HEAD, codex_state=state,
                                             graphite=(HEAD, "skipped"))["state"], "pending")

    def test_foreign_commit_does_not_count(self):
        self.assertEqual(self.status(codex=FOREIGN, graphite=(FOREIGN, "success"))["state"], "pending")

    def test_earlier_pr_commit_still_counts(self):
        self.assertEqual(self.status(codex=OLD)["state"], "success")
        self.assertEqual(self.status(graphite=(OLD, "success"))["state"], "success")

    def test_closed_or_non_main_pr_writes_nothing(self):
        self.assertEqual(self.run_gate(codex=HEAD, state="closed"), [])
        self.assertEqual(self.run_gate(codex=HEAD, base="release"), [])

    # Approval.

    def test_codex_no_findings_approves(self):
        result = self.approval(codex=OLD)
        self.assertEqual(result["commit_id"], HEAD)
        self.assertIn(f"Codex reviewed `{OLD}`", result["body"])

    def test_versioned_clean_receipt_resolves_short_and_full_pr_commits(self):
        for commit in (HEAD[:10], HEAD):
            with self.subTest(commit=commit):
                result = self.approval(receipts=[receipt(commit)])
                self.assertIn(f"Codex reviewed `{HEAD}`", result["body"])

    def test_receipt_cannot_be_forged_by_human_or_another_bot(self):
        for actor in ({"__typename": "User", "login": CODEX},
                      {"__typename": "User", "login": "joshsny"},
                      {"__typename": "Bot", "login": "another-bot"}):
            with self.subTest(actor=actor):
                forged = receipt()
                forged["author"] = actor
                self.assertIsNone(self.approval(receipts=[forged]))

    def test_receipt_requires_trusted_complete_edit_history(self):
        for editor in ({"__typename": "User", "login": "joshsny"}, None):
            changed = receipt()
            changed["userContentEdits"]["nodes"] = [{"editor": editor, "diff": "forged clean body"}]
            self.assertIsNone(self.approval(receipts=[changed]))
        incomplete = receipt()
        incomplete["userContentEdits"]["pageInfo"]["hasNextPage"] = True
        self.assertIsNone(self.approval(receipts=[incomplete]))
        trusted = receipt()
        trusted["userContentEdits"]["nodes"] = [{"editor": {"__typename": "Bot", "login": CODEX}, "diff": "trusted edit"}]
        self.assertIsNotNone(self.approval(receipts=[trusted]))

    def test_receipt_rejects_ambiguous_foreign_or_multiple_commit_references(self):
        self.assertIsNone(self.approval(receipts=[receipt()], mid=HEAD[:10]+"d"*30))
        self.assertIsNone(self.approval(receipts=[receipt(FOREIGN[:10])]))
        multiple = receipt()
        multiple["body"] += f"**Reviewed commit:** `{MID[:10]}`\n"
        self.assertIsNone(self.approval(receipts=[multiple]))
        self.assertIsNotNone(self.approval(receipts=[receipt(HEAD)], mid=HEAD[:10]+"d"*30))

    def test_receipt_requires_explicit_clean_result_and_version_marker(self):
        for replacement in ("Here are some automated review suggestions for this pull request.",
                            "Codex review is running.", "Review failed."):
            changed = receipt()
            changed["body"] = changed["body"].replace("Codex Review: Didn't find any major issues. :rocket:", replacement)
            self.assertIsNone(self.approval(receipts=[changed]))
        for marker in ("", "<!-- codex-review-receipt:v2 -->"):
            changed = receipt()
            changed["body"] = changed["body"].replace("<!-- codex-review-receipt:v1 -->", marker)
            self.assertIsNone(self.approval(receipts=[changed]))
        contradictory = receipt()
        contradictory["body"] += P2
        self.assertIsNone(self.approval(receipts=[contradictory]))
        quoted = receipt()
        quoted["body"] = "Example receipt:\n```\n" + quoted["body"] + "```\n"
        self.assertIsNone(self.approval(receipts=[quoted]))

    def test_clean_receipt_does_not_override_inline_p1_or_unresolved_threads(self):
        self.assertIsNone(self.approval(receipts=[receipt()],
            reviews=[(CODEX, "COMMENTED", HEAD, [P1])], threads=[(CODEX, P1, True)]))
        self.assertIsNone(self.approval(receipts=[receipt()], threads=[("joshsny", "unresolved", False)]))

    def test_receipt_parser_itself_filters_inline_blocking_findings(self):
        parse = runpy.run_path(str(ROOT / 'tools/ci/codex_receipts.py'))['clean_commits']
        for badge in (P1, P1.replace('P1', 'P0')):
            finding = {"login": CODEX+'[bot]', "reply": None, "commit": HEAD, "body": badge}
            self.assertEqual(parse([receipt()], [HEAD, OLD], [finding]), [])
            self.assertEqual(parse([receipt()], [HEAD, OLD], [{**finding, "commit": OLD}]), [HEAD])
            self.assertEqual(parse([receipt()], [HEAD, OLD], [{**finding, "login": 'joshsny'}]), [HEAD])

    def test_newer_clean_receipt_clears_old_p1_but_same_commit_does_not(self):
        history = {"reviews": [(CODEX, "COMMENTED", OLD, [P1])], "threads": [(CODEX, P1, True)]}
        self.assertIsNotNone(self.approval(receipts=[receipt()], **history))
        self.assertIsNone(self.approval(receipts=[receipt(OLD[:10])], **history))

    def test_graphite_alone_approves(self):
        result = self.approval(graphite=(HEAD, "success"))
        self.assertIn(f"Graphite AI Reviews succeeded on `{HEAD}`", result["body"])

    def test_codex_p2_review_with_resolved_thread_approves(self):
        self.assertIsNotNone(self.approval(
            codex=HEAD, codex_findings=True,
            reviews=[(CODEX, "COMMENTED", HEAD, [P2])], threads=[(CODEX, P2, True)]))

    def test_any_unresolved_thread_blocks(self):
        self.assertIsNone(self.approval(codex=HEAD, threads=[("graphite-app", "Consider this", False)]))
        self.assertIsNone(self.approval(codex=HEAD, threads=[("joshsny", "note", False)]))

    def test_skipped_graphite_and_running_codex_do_not_approve(self):
        self.assertIsNone(self.approval(codex=HEAD, codex_state="running", graphite=(HEAD, "skipped")))

    def test_bot_changes_requested_blocks_until_superseded(self):
        self.assertIsNone(self.approval(
            codex=HEAD, reviews=[("graphite-app", "CHANGES_REQUESTED", OLD, [])]))
        self.assertIsNotNone(self.approval(
            codex=HEAD, reviews=[("graphite-app", "CHANGES_REQUESTED", OLD, []),
                                 ("graphite-app", "COMMENTED", HEAD, []),
                                 ("graphite-app", "APPROVED", HEAD, [])]))

    def test_does_not_approve_twice_but_reapproves_after_dismissal(self):
        self.assertEqual(self.run_gate(codex=HEAD, reviews=[(APP, "APPROVED", OLD, [])])[1:], [])
        self.assertIsNotNone(self.approval(codex=HEAD, reviews=[(APP, "DISMISSED", OLD, [])]))

    def test_does_not_review_own_pr(self):
        self.assertIsNone(self.review(codex=HEAD, author="gradiated-review[bot]"))

    def test_foreign_commit_does_not_approve(self):
        self.assertIsNone(self.approval(codex=FOREIGN, reviews=[(CODEX, "COMMENTED", FOREIGN, [P2])]))

    # Rule (b): a Codex P0/P1 needs a clean Codex review of a newer commit.

    def test_resolved_p1_without_newer_clean_codex_review_does_not_approve(self):
        writes = self.run_gate(graphite=(HEAD, "success"), codex=OLD, codex_findings=True,
                               reviews=[(CODEX, "COMMENTED", OLD, [P1])], threads=[(CODEX, P1, True)])
        review = [w for w in writes if w["kind"] == "review"][-1]
        self.assertEqual(review["event"], "COMMENT")
        self.assertIn("Waiting for a clean AI review of the latest fix", review["body"])
        self.assertIn(f"`{OLD[:7]}`", review["body"])

    def test_clean_codex_review_of_newer_commit_clears_p1(self):
        result = self.approval(codex=MID, reviews=[(CODEX, "COMMENTED", OLD, [P1])],
                               threads=[(CODEX, P1, True)])
        self.assertIn("followed by a clean Codex review", result["body"])

    def test_codex_p2_only_review_of_newer_commit_clears_p1(self):
        self.assertIsNotNone(self.approval(
            reviews=[(CODEX, "COMMENTED", OLD, [P1]), (CODEX, "COMMENTED", HEAD, [P2])],
            threads=[(CODEX, P1, True), (CODEX, P2, True)]))

    def test_p1_on_the_same_commit_as_the_clean_review_does_not_count(self):
        self.assertIsNone(self.approval(codex=HEAD, reviews=[(CODEX, "COMMENTED", HEAD, [P1])],
                                        threads=[(CODEX, P1, True)]))

    def test_open_codex_p1_is_listed_with_link(self):
        review = self.review(graphite=(HEAD, "success"), reviews=[(CODEX, "COMMENTED", OLD, [P1])],
                             threads=[(CODEX, P1, False), ("joshsny", "why?", False)])
        self.assertEqual(review["event"], "COMMENT")
        self.assertIn("- Open Codex P1: [Fix it](https://t/0)", review["body"])
        self.assertIn("- Unresolved thread by @joshsny on `x.py`: https://t/1", review["body"])

    # Asking Codex to review the fix.

    def test_asks_codex_once_per_head_after_a_fix_is_pushed(self):
        args = dict(graphite=(HEAD, "success"), reviews=[(CODEX, "COMMENTED", OLD, [P1])],
                    threads=[(CODEX, P1, True)])
        comments = [w for w in self.run_gate(**args) if w["kind"] == "comment"]
        self.assertEqual(len(comments), 1)
        self.assertTrue(comments[0]["body"].startswith("@codex review"))
        self.assertIn(f"gradiated-review-codex-request:{HEAD}", comments[0]["body"])
        again = self.run_gate(issue_comments=[(APP, comments[0]["body"])], **args)
        self.assertEqual([w for w in again if w["kind"] == "comment"], [])

    def test_asking_codex_can_be_turned_off(self):
        self.assertEqual([w for w in self.run_gate(graphite=(HEAD, "success"), ask_codex="false",
                                                   reviews=[(CODEX, "COMMENTED", OLD, [P1])],
                                                   threads=[(CODEX, P1, True)])
                          if w["kind"] == "comment"], [])

    def test_does_not_ask_codex_before_a_fix_or_while_it_runs(self):
        self.assertEqual([w for w in self.run_gate(reviews=[(CODEX, "COMMENTED", HEAD, [P1])],
                                                   threads=[(CODEX, P1, False)])
                          if w["kind"] == "comment"], [])
        self.assertEqual([w for w in self.run_gate(codex=HEAD, codex_state="running",
                                                   reviews=[(CODEX, "COMMENTED", OLD, [P1])],
                                                   threads=[(CODEX, P1, True)])
                          if w["kind"] == "comment"], [])

    # Comment reviews: deduplicated by state, approvals dismissed when stale.

    def test_same_outstanding_items_are_not_posted_twice(self):
        args = dict(codex=HEAD, threads=[("joshsny", "note", False)])
        first = self.review(**args)
        self.assertEqual(first["event"], "COMMENT")
        self.assertIsNone(self.review(reviews=[(APP, "COMMENTED", HEAD, [], first["body"])], **args))
        changed = dict(codex=HEAD, threads=[("joshsny", "note", False), ("joshsny", "more", False)])
        self.assertIsNotNone(self.review(reviews=[(APP, "COMMENTED", HEAD, [], first["body"])], **changed))

    def test_new_finding_dismisses_the_apps_approval(self):
        writes = self.run_gate(codex=HEAD, threads=[(CODEX, P1, False)],
                               reviews=[(APP, "APPROVED", OLD, []), (CODEX, "COMMENTED", HEAD, [P1])])
        kinds = [w["kind"] for w in writes]
        self.assertIn("dismissal", kinds)
        self.assertEqual(writes[kinds.index("dismissal")]["endpoint"],
                         "repos/Gradiated/gradiated/pulls/714/reviews/0/dismissals")
        self.assertEqual([w for w in writes if w["kind"] == "review"][-1]["event"], "COMMENT")

    # Requests from people: @gradiated-review or /review.

    def test_writer_request_reacts_and_reposts_unchanged_state(self):
        args = dict(codex=HEAD, threads=[("joshsny", "note", False)])
        body = self.review(**args)["body"]
        writes = self.run_gate(event="issue_comment", commenter_type="User",
                               reviews=[(APP, "COMMENTED", HEAD, [], body)], **args)
        self.assertEqual(writes[0]["kind"], "reaction")
        self.assertEqual([w for w in writes if w["kind"] == "review"][-1]["event"], "COMMENT")

    def test_non_writer_request_is_ignored(self):
        for role in ("read", "triage", "none"):
            with self.subTest(role=role):
                self.assertEqual(self.run_gate(codex=HEAD, event="issue_comment",
                                               commenter_type="User", role=role), [])

    def test_status_uses_status_token(self):
        workflow = (ROOT / ".github/workflows/ai-review-gate.yml").read_text()
        self.assertIn('GH_TOKEN="$STATUS_TOKEN" gh api "repos/$REPO/statuses/$head"', workflow)

    def test_requests_from_bots_do_not_start_the_job(self):
        workflow = (ROOT / ".github/workflows/ai-review-gate.yml").read_text()
        self.assertIn("github.event.comment.user.type == 'User'", workflow)


if __name__ == "__main__":
    unittest.main()
