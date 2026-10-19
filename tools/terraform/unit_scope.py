"""Select the same Terragrunt change scope for PR previews and production applies."""

import argparse
import json
import re
import subprocess

GLOBAL_INPUTS = {"mise.toml", "infra/environments/prod/us-east-1/terraform/root.hcl"}


def command(*args):
    return subprocess.check_output(args, text=True)


def last_apply(runs, jobs):
    for run in runs:
        if run["event"] not in {"push", "workflow_dispatch"}:
            continue
        if any(job["name"] == "Production apply" and job["conclusion"] == "success"
               for job in jobs(run["databaseId"])):
            return run["headSha"]
    raise ValueError("No successful production apply found; review a full plan and use workflow_dispatch.")


def scope(base, head, changed, force_all=False):
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("Invalid target commit")
    if force_all:
        return ""
    if not re.fullmatch(r"[0-9a-f]{40}", base or ""):
        raise ValueError("Invalid apply baseline")
    return "" if GLOBAL_INPUTS.intersection(changed) else f"...[{base}...{head}]"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--force-all", action="store_true")
    args = parser.parse_args()
    if args.force_all:
        print("filter=" + scope(None, args.head, [], True))
        print("base=manual-full-apply")
        return
    runs = json.loads(command("gh", "run", "list", "--repo", args.repo, "--workflow", "terraform.yml",
                              "--branch", "main", "--status", "success", "--limit", "100",
                              "--json", "databaseId,headSha,event"))

    def jobs(run_id):
        pages = json.loads(command("gh", "api", "--paginate", "--slurp",
                                   f"repos/{args.repo}/actions/runs/{run_id}/jobs?per_page=100"))
        return [job for page in pages for job in page["jobs"]]

    base = last_apply(runs, jobs)
    if subprocess.run(["git", "merge-base", "--is-ancestor", base, args.head], check=False).returncode:
        raise ValueError("The successful apply is not an ancestor; update the PR before planning.")
    changed = command("git", "diff", "--name-only", base, args.head).splitlines()
    print("filter=" + scope(base, args.head, changed))
    print("base=" + base)


if __name__ == "__main__":
    main()
