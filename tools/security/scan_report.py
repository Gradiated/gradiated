#!/usr/bin/env python3
"""Summarize security scanner reports for GitHub job summaries and apply CI gates.

Markdown goes to stdout so a workflow can append it to $GITHUB_STEP_SUMMARY.
Secret values never leave the scanner report: the gitleaks summary prints only
the rule, file, line and commit.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]
MAX_ROWS = 50
IGNORE_ID = re.compile(r"^(CVE-\d{4}-\d+|GHSA(-[0-9a-z]{4}){3}|[A-Z][A-Z0-9]*-[A-Z0-9-]+)(\s+exp:\d{4}-\d{2}-\d{2})?$")


def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(header: list[str], rows: list[list[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(cell(value) for value in row) + " |" for row in rows[:MAX_ROWS]]
    if len(rows) > MAX_ROWS:
        lines.append(f"\n{len(rows) - MAX_ROWS} more rows are in the report artifact.")
    return lines


def gitleaks(report: list[dict]) -> tuple[list[str], int]:
    if not report:
        return ["### Gitleaks", "", "No secrets found."], 0
    rules = collections.Counter(finding["RuleID"] for finding in report)
    lines = ["### Gitleaks", "", f"**{len(report)} potential secrets found.** Values are redacted.", ""]
    lines += table(["Rule", "Findings"], [[rule, count] for rule, count in rules.most_common()])
    lines += ["", *table(
        ["Rule", "File", "Line", "Commit"],
        [[f["RuleID"], f["File"], f["StartLine"], f.get("Commit", "")[:12]] for f in report],
    )]
    lines += [
        "",
        "If a finding is a real credential, rotate it first, then remove it from the branch.",
        "If it is a false positive, add the narrowest allowlist to `.gitleaks.toml` or its",
        "fingerprint to `.gitleaksignore`, with a comment saying why it is not a secret.",
    ]
    return lines, 1


def semgrep(report: dict) -> tuple[list[str], int]:
    results = report.get("results", [])
    errors = report.get("errors", [])
    severities = collections.Counter(result["extra"]["severity"] for result in results)
    lines = ["### Semgrep (report only)", ""]
    lines.append(f"{len(results)} findings: " + (", ".join(f"{k} {v}" for k, v in sorted(severities.items())) or "none") + ".")
    if errors:
        lines.append(f"{len(errors)} files or rules produced scan errors; see the report artifact.")
    if results:
        rules = collections.Counter((r["extra"]["severity"], r["check_id"]) for r in results)
        lines += ["", *table(["Severity", "Rule", "Findings"], [[s, rule, n] for (s, rule), n in rules.most_common()])]
        lines += ["", *table(
            ["Severity", "Rule", "Location"],
            [[r["extra"]["severity"], r["check_id"].rsplit(".", 1)[-1], f"{r['path']}:{r['start']['line']}"] for r in results],
        )]
    return lines, 0


def trivy(report: dict, name: str, enforce: bool) -> tuple[list[str], int]:
    counts: collections.Counter[tuple[str, bool]] = collections.Counter()
    blocking, fixable_high = [], []
    image = report.get("ArtifactName", name)
    for result in report.get("Results") or []:
        # The OS target repeats the full image reference; keep only "(debian 12.15)".
        target = result["Target"].replace(image, "").strip() or result["Target"]
        for vuln in result.get("Vulnerabilities") or []:
            fixed = bool(vuln.get("FixedVersion"))
            counts[(vuln["Severity"], fixed)] += 1
            row = [vuln["VulnerabilityID"], vuln["Severity"], vuln["PkgName"], vuln.get("InstalledVersion", ""),
                   vuln.get("FixedVersion", ""), target]
            if fixed and vuln["Severity"] == "CRITICAL":
                blocking.append(row)
            elif fixed and vuln["Severity"] == "HIGH":
                fixable_high.append(row)
    lines = [f"### Trivy: {name}", "", f"`{image}`", ""]
    lines += table(
        ["Severity", "Fix available", "No fix yet"],
        [[s, counts[(s, True)], counts[(s, False)]] for s in SEVERITIES if counts[(s, True)] or counts[(s, False)]] or [["none", 0, 0]],
    )
    if blocking:
        verdict = "blocks this release" if enforce else "is reported only for this image"
        lines += ["", f"**{len(blocking)} CRITICAL vulnerabilities with a fix available; this {verdict}.**", ""]
        lines += table(["ID", "Severity", "Package", "Installed", "Fixed", "Target"], blocking)
        if enforce:
            lines += ["", "Upgrade the package or base image. To accept the risk temporarily, add the ID to",
                      "`.trivyignore` with a justification comment and an `exp:` date."]
    if fixable_high:
        lines += ["", f"<details><summary>{len(fixable_high)} HIGH vulnerabilities with a fix available (not blocking)</summary>", ""]
        lines += table(["ID", "Severity", "Package", "Installed", "Fixed", "Target"], fixable_high)
        lines += ["", "</details>"]
    return lines, int(enforce and bool(blocking))


def read_semicolon_csv(paths: list[Path]) -> list[dict[str, str]]:
    rows = []
    for path in paths:
        with path.open(newline="") as handle:
            rows += [{k.lower(): v for k, v in row.items() if k} for row in csv.DictReader(handle, delimiter=";")]
    return rows


def prowler(directory: Path) -> tuple[list[str], int]:
    """Summarize Prowler's findings CSV and SOC 2 compliance CSV (semicolon-separated)."""
    rows = read_semicolon_csv(sorted(directory.glob("compliance/*soc2*.csv")))
    lines = ["### Prowler SOC 2 (AWS)", ""]
    if not rows:
        return lines + ["No SOC 2 compliance output was found; see the job log."], 0
    statuses = collections.Counter(row.get("status", "UNKNOWN") for row in rows)
    lines.append("SOC 2 checks by status: " + ", ".join(f"{k} {v}" for k, v in sorted(statuses.items())) + ".")
    findings = read_semicolon_csv(sorted(directory.glob("*.csv")))
    if findings:
        by_severity = collections.Counter((f.get("severity", "unknown").upper(), f.get("status", "UNKNOWN")) for f in findings)
        lines += ["", *table(
            ["Severity", "FAIL", "PASS", "MANUAL"],
            [[s, by_severity[(s, "FAIL")], by_severity[(s, "PASS")], by_severity[(s, "MANUAL")]]
             for s in SEVERITIES + ["INFORMATIONAL"] if any(by_severity[(s, st)] for st in ("FAIL", "PASS", "MANUAL"))],
        )]
        failed = collections.Counter(
            (f.get("severity", "").upper(), f.get("check_id", "?"), f.get("check_title", ""))
            for f in findings if f.get("status") == "FAIL"
        )
        order = {s: i for i, s in enumerate(SEVERITIES)}
        top = sorted(failed.items(), key=lambda item: (order.get(item[0][0], len(order)), -item[1]))[:20]
        if top:
            lines += ["", "Top failing checks (failed resources):", "", *table(
                ["Severity", "Check", "Title", "Failed"], [[s, check, title, n] for (s, check, title), n in top])]
    failing = collections.Counter(row.get("requirements_id", "?") for row in rows if row.get("status") == "FAIL")
    if failing:
        lines += ["", *table(["SOC 2 requirement", "Failed checks"], [[req, n] for req, n in sorted(failing.items())])]
    lines += ["", "The full report (HTML, CSV and OCSF JSON) is in the workflow artifact."]
    return lines, 0


def check_trivyignore(text: str) -> list[str]:
    """Every ignored ID needs a justification comment directly above its block."""
    problems, justified = [], False
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            justified = False
        elif line.startswith("#"):
            justified = justified or bool(line.lstrip("#").strip())
        elif not IGNORE_ID.match(line):
            problems.append(f"line {number}: expected a vulnerability ID, optionally followed by exp:YYYY-MM-DD")
        elif not justified:
            problems.append(f"line {number}: {line.split()[0]} needs a justification comment directly above it")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("gitleaks", "semgrep"):
        commands.add_parser(name).add_argument("report", type=Path)
    trivy_parser = commands.add_parser("trivy")
    trivy_parser.add_argument("report", type=Path)
    trivy_parser.add_argument("--name", required=True)
    trivy_parser.add_argument("--enforce", action="store_true", help="Fail on CRITICAL vulnerabilities with a fix.")
    commands.add_parser("check-trivyignore").add_argument("path", type=Path)
    commands.add_parser("prowler").add_argument("directory", type=Path)
    args = parser.parse_args(argv)

    if args.command == "prowler":
        lines, status = prowler(args.directory)
        print("\n".join(lines) + "\n")
        return status

    if args.command == "check-trivyignore":
        problems = check_trivyignore(args.path.read_text()) if args.path.exists() else []
        for problem in problems:
            print(f"{args.path}: {problem}", file=sys.stderr)
        return int(bool(problems))

    report = json.loads(args.report.read_text() or "null")
    if args.command == "gitleaks":
        lines, status = gitleaks(report or [])
    elif args.command == "semgrep":
        lines, status = semgrep(report or {})
    else:
        lines, status = trivy(report or {}, args.name, args.enforce)
    print("\n".join(lines) + "\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
