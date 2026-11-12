#!/usr/bin/env python3
"""Build the repository .env from the shared development secret.

Reads gradiated/dev/env from AWS Secrets Manager and writes .env with mode
0600. Variables in the existing .env that the secret does not hold are kept
in a local-only section. Prints variable names only, never values.

Uses the gradiated-restricted profile by default, which every collaborator
has. Creates that AWS profile when it is missing and signs in when the
session has expired.
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

SECRET_ID = "gradiated/dev/env"
REGION = "us-east-1"
ACCOUNT_ID = "873716897517"
SSO_SESSION = {
    "sso_start_url": "https://d-c3676db5af.awsapps.com/start",
    "sso_region": "eu-north-1",
    "sso_registration_scopes": "sso:account:access",
}
# Profiles are named after their permission sets, except the admin profile.
PERMISSION_SETS = {"gradiated-admin": "AdministratorAccess"}
ROOT = Path(__file__).resolve().parents[2]
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
LOCAL_HEADER = "# Local only: not in gradiated/dev/env"


def configured(*arguments: str) -> bool:
    return not subprocess.run(
        ["aws", "configure", "get", *arguments], capture_output=True
    ).returncode


def ensure_profile(profile: str) -> None:
    """Create the SSO profile for a Gradiated permission set if it is missing."""
    if configured("sso_role_name", "--profile", profile):
        return
    # `aws configure set` cannot write an sso-session section; append it.
    config = Path(os.environ.get("AWS_CONFIG_FILE", Path.home() / ".aws" / "config")).expanduser()
    if "[sso-session gradiated]" not in (config.read_text() if config.exists() else ""):
        config.parent.mkdir(parents=True, exist_ok=True)
        with config.open("a") as handle:
            handle.write("\n[sso-session gradiated]\n")
            handle.writelines(f"{key} = {value}\n" for key, value in SSO_SESSION.items())
    settings = {"sso_session": "gradiated", "sso_account_id": ACCOUNT_ID,
                "sso_role_name": PERMISSION_SETS.get(profile, profile), "region": REGION}
    for key, value in settings.items():
        subprocess.run(["aws", "configure", "set", key, value, "--profile", profile], check=True)
    print(f"Added the {profile} AWS profile.")


def fetch(profile: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["aws", "secretsmanager", "get-secret-value", "--secret-id", SECRET_ID,
         "--profile", profile, "--region", REGION,
         "--query", "SecretString", "--output", "text"],
        capture_output=True, text=True,
    )


def read_secret(profile: str) -> dict[str, str]:
    ensure_profile(profile)
    result = fetch(profile)
    # A missing assignment is AccessDenied (Secrets Manager) or ForbiddenException
    # (SSO); signing in again cannot fix either.
    if result.returncode and not any(code in result.stderr for code in ("AccessDenied", "ForbiddenException")):
        print(f"Signing in to AWS as {profile}; approve the request in your browser.")
        subprocess.run(["aws", "sso", "login", "--profile", profile], check=True)
        result = fetch(profile)
    if result.returncode:
        sys.exit(
            f"Could not read {SECRET_ID} with the {profile} profile. Ask an "
            "administrator to add you with the restricted access level in "
            "infra/bootstrap/identity-center/people.tf."
        )
    values = json.loads(result.stdout)
    for name, value in values.items():
        # A line separator would split the value when .env is read back, and
        # shells drop NUL bytes, so neither survives .env.
        if (not NAME.fullmatch(name) or not isinstance(value, str)
                or value.splitlines() not in ([], [value]) or "\0" in value):
            sys.exit(f"{SECRET_ID} holds an entry that cannot go in .env: {name}")
    return values


def single_value(value: str) -> bool:
    """Whether the text after NAME= is one complete shell word.

    Refuses unclosed quotes, trailing-backslash continuations and compound
    lines such as `A=1; B=2`, whose other assignments filtering would lose.
    """
    lexer = shlex.shlex(value, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return len(list(lexer)) <= 1
    except ValueError:
        return False


def read_existing(path: Path) -> list[tuple[str, str]]:
    """(name, line) for every assignment, in file order, duplicates included.

    Refuses files this script cannot carry over.
    """
    if not path.exists():
        return []
    lines = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, separator, value = line.partition("=")
        name = name.strip().removeprefix("export ").strip()
        # Name the line number only: a stray line may be part of a secret.
        if not separator or not NAME.fullmatch(name) or not single_value(value):
            sys.exit(
                f"{path} line {number} is not a single-line NAME=value assignment. "
                "Move multi-line values to .env.local, which is loaded after .env, and run again."
            )
        lines.append((name, line))
    return lines


def quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="gradiated-restricted")
    arguments = parser.parse_args()

    # Never follow a symlink: replacing it would overwrite the file it names.
    target = ROOT / ".env"
    if target.is_symlink():
        sys.exit(f"{target} is a symlink. Remove it or point mise at a regular file, and run again.")
    values = read_secret(arguments.profile)
    existing = read_existing(target)
    # Keep every local line in file order: one may refer to another before it,
    # and a repeated name changes meaning part way through the file.
    kept = [(name, line) for name, line in existing if name not in values]

    lines = [f"# Built from {SECRET_ID} by `mise run env:build`; rerun to refresh."]
    lines += [f"{name}={quote(values[name])}" for name in sorted(values)]
    if kept:
        lines += ["", LOCAL_HEADER, *(line for _, line in kept)]

    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=".env.")
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write("\n".join(lines) + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    except BaseException:
        os.unlink(temporary)
        raise

    added = sorted(set(values) - {name for name, _ in existing})
    print(f"Wrote {target} with {len(values)} variables from {SECRET_ID}.")
    if added:
        print("Added:", ", ".join(added))
    if kept:
        print("Kept local-only:", ", ".join(dict.fromkeys(name for name, _ in kept)))


if __name__ == "__main__":
    main()
