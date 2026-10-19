import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scan_report import check_trivyignore, gitleaks, main, prowler, semgrep, trivy  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def vuln(identifier, severity, fixed=""):
    return {"VulnerabilityID": identifier, "Severity": severity, "PkgName": "pkg",
            "InstalledVersion": "1.0", "FixedVersion": fixed}


class TrivyTest(unittest.TestCase):
    report = {"ArtifactName": "registry/image@sha256:abc", "Results": [{"Target": "debian", "Vulnerabilities": [
        vuln("CVE-1", "CRITICAL", "1.1"), vuln("CVE-2", "CRITICAL"), vuln("CVE-3", "HIGH", "1.2"), vuln("CVE-4", "HIGH")]}]}

    def test_enforce_fails_only_on_fixable_critical(self):
        lines, status = trivy(self.report, "product", enforce=True)
        self.assertEqual(status, 1)
        text = "\n".join(lines)
        self.assertIn("CVE-1", text)
        self.assertNotIn("CVE-2 |", text)
        self.assertIn("| CRITICAL | 1 | 1 |", text)
        self.assertIn("| HIGH | 1 | 1 |", text)

    def test_unfixed_critical_and_high_do_not_fail(self):
        report = {"Results": [{"Target": "t", "Vulnerabilities": [vuln("CVE-2", "CRITICAL"), vuln("CVE-3", "HIGH", "1.2")]}]}
        self.assertEqual(trivy(report, "gateway", enforce=True)[1], 0)

    def test_report_mode_never_fails(self):
        self.assertEqual(trivy(self.report, "gpu-base", enforce=False)[1], 0)

    def test_clean_image(self):
        lines, status = trivy({"Results": None}, "proxy", enforce=True)
        self.assertEqual(status, 0)
        self.assertIn("| none | 0 | 0 |", "\n".join(lines))


class GitleaksTest(unittest.TestCase):
    def test_summary_never_contains_secret_or_match(self):
        finding = {"RuleID": "aws-access-token", "File": "a.py", "StartLine": 3, "Commit": "0123456789abcdef",
                   "Secret": "AKIAREALSECRETVALUE1", "Match": "key=AKIAREALSECRETVALUE1"}
        lines, status = gitleaks([finding])
        self.assertEqual(status, 1)
        self.assertNotIn("AKIAREALSECRETVALUE1", "\n".join(lines))
        self.assertIn("| aws-access-token | a.py | 3 | 0123456789ab |", "\n".join(lines))

    def test_clean(self):
        self.assertEqual(gitleaks([])[1], 0)


class SemgrepTest(unittest.TestCase):
    def test_report_only(self):
        result = {"check_id": "a.b.rule", "path": "x.ts", "start": {"line": 2}, "extra": {"severity": "ERROR"}}
        lines, status = semgrep({"results": [result], "errors": []})
        self.assertEqual(status, 0)
        self.assertIn("ERROR 1", "\n".join(lines))


class TrivyignoreTest(unittest.TestCase):
    def test_requires_justification_comment(self):
        self.assertEqual(check_trivyignore("# Accepted: not reachable.\nCVE-2026-1 exp:2026-11-14\n"), [])
        self.assertEqual(len(check_trivyignore("CVE-2026-1\n")), 1)
        self.assertEqual(len(check_trivyignore("#\nCVE-2026-1\n")), 1)
        self.assertEqual(len(check_trivyignore("# Reason.\n\nCVE-2026-1\n")), 1)

    def test_one_comment_covers_its_block(self):
        self.assertEqual(check_trivyignore("# Same base image fix.\nCVE-2026-1\nCVE-2026-2\n"), [])

    def test_rejects_malformed_entries(self):
        self.assertEqual(len(check_trivyignore("# Reason.\nCVE-2026-1 forever\n")), 1)

    def test_repository_file_is_valid(self):
        self.assertEqual(check_trivyignore((ROOT / ".trivyignore").read_text()), [])


class ProwlerTest(unittest.TestCase):
    def test_counts_soc2_statuses_and_failing_requirements(self):
        with tempfile.TemporaryDirectory() as directory:
            compliance = Path(directory) / "compliance"
            compliance.mkdir()
            (compliance / "prowler-soc2_aws.csv").write_text(
                "PROVIDER;REQUIREMENTS_ID;STATUS;CHECKID\n"
                "aws;cc_6_1;FAIL;iam_root_mfa_enabled\n"
                "aws;cc_6_1;PASS;iam_password_policy\n"
                "aws;cc_7_2;FAIL;cloudtrail_multi_region_enabled\n"
            )
            (Path(directory) / "prowler-soc2.csv").write_text(
                "CHECK_ID;CHECK_TITLE;STATUS;SEVERITY\n"
                "iam_root_mfa_enabled;Root MFA;FAIL;critical\n"
                "iam_password_policy;Password policy;PASS;medium\n"
                "cloudtrail_multi_region_enabled;Multi-region trail;FAIL;high\n"
                "cloudtrail_multi_region_enabled;Multi-region trail;FAIL;high\n"
            )
            lines, status = prowler(Path(directory))
        text = "\n".join(lines)
        self.assertEqual(status, 0)
        self.assertIn("FAIL 2, PASS 1", text)
        self.assertIn("| cc_6_1 | 1 |", text)
        self.assertIn("| CRITICAL | 1 | 0 | 0 |", text)
        self.assertIn("| HIGH | 2 | 0 | 0 |", text)
        self.assertIn("| HIGH | cloudtrail_multi_region_enabled | Multi-region trail | 2 |", text)
        self.assertLess(text.index("iam_root_mfa_enabled | Root MFA"), text.index("cloudtrail_multi_region_enabled | Multi"))

    def test_missing_output_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn("No SOC 2 compliance output", "\n".join(prowler(Path(directory))[0]))


class CliTest(unittest.TestCase):
    def test_trivy_cli_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(TrivyTest.report))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["trivy", str(path), "--name", "product", "--enforce"]), 1)
                self.assertEqual(main(["trivy", str(path), "--name", "product"]), 0)


if __name__ == "__main__":
    unittest.main()
