"""`gradctl env build`: build the repository .env from the shared development secret.

Reads gradiated/dev/env from AWS Secrets Manager and writes .env with mode
0600. With --with-fde it also reads gradiated/dev/fde, the forward-deployed
engineering keys for customer work, whose values win where both secrets name a
variable. Variables in the existing .env that the secrets do not hold are kept
in a local-only section. Prints variable names only, never values.

Uses the gradiated-restricted profile by default, which every collaborator
has. Creates that AWS profile when it is missing and signs in when the
session has expired.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .core import Context, DependencyMissing, Meta, Result, group, leaf

SECRET_ID = "gradiated/dev/env"
FDE_SECRET_ID = "gradiated/dev/fde"
REGION = "us-east-1"
ACCOUNT_ID = "873716897517"
SSO_SESSION = {
    "sso_start_url": "https://d-c3676db5af.awsapps.com/start",
    "sso_region": "eu-north-1",
    "sso_registration_scopes": "sso:account:access",
}
# Profiles are named after their permission sets, except the admin profile.
PERMISSION_SETS = {"gradiated-admin": "AdministratorAccess"}
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


def fetch(profile: str, secret_id: str = SECRET_ID) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["aws", "secretsmanager", "get-secret-value", "--secret-id", secret_id,
         "--profile", profile, "--region", REGION,
         "--query", "SecretString", "--output", "text"],
        capture_output=True, text=True,
    )


def read_secret(profile: str, secret_id: str = SECRET_ID) -> dict[str, str]:
    ensure_profile(profile)
    result = fetch(profile, secret_id)
    # A missing assignment is AccessDenied (Secrets Manager) or ForbiddenException
    # (SSO); signing in again cannot fix either.
    if result.returncode and not any(code in result.stderr for code in ("AccessDenied", "ForbiddenException")):
        print(f"Signing in to AWS as {profile}; approve the request in your browser.")
        subprocess.run(["aws", "sso", "login", "--profile", profile], check=True)
        result = fetch(profile, secret_id)
    if result.returncode:
        sys.exit(
            f"Could not read {secret_id} with the {profile} profile. Ask an "
            "administrator to add you with the restricted access level in "
            "infra/bootstrap/identity-center/people.tf."
        )
    values = json.loads(result.stdout)
    for name, value in values.items():
        # A line separator would split the value when .env is read back, and
        # shells drop NUL bytes, so neither survives .env.
        if (not NAME.fullmatch(name) or not isinstance(value, str)
                or value.splitlines() not in ([], [value]) or "\0" in value):
            sys.exit(f"{secret_id} holds an entry that cannot go in .env: {name}")
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


def build(ctx: Context) -> Result:
    if not shutil.which('aws'):
        raise DependencyMissing('aws', 'install the AWS CLI v2 (`mise install`)')
    # Never follow a symlink: replacing it would overwrite the file it names.
    target = ctx.repo() / ".env"
    if target.is_symlink():
        sys.exit(f"{target} is a symlink. Remove it or point mise at a regular file, and run again.")
    values = read_secret(ctx.args.profile)
    sources, overridden = [SECRET_ID], []
    if ctx.args.with_fde:
        fde = read_secret(ctx.args.profile, FDE_SECRET_ID)
        overridden = sorted(set(values) & set(fde))
        values.update(fde)
        sources.append(FDE_SECRET_ID)
    source = " and ".join(sources)
    existing = read_existing(target)
    # Keep every local line in file order: one may refer to another before it,
    # and a repeated name changes meaning part way through the file.
    kept = [(name, line) for name, line in existing if name not in values]

    command = "gradctl env build --with-fde" if ctx.args.with_fde else "gradctl env build"
    lines = [f"# Built from {source} by `{command}`; rerun it to refresh."]
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
    kept_names = list(dict.fromkeys(name for name, _ in kept))
    text = [f"Wrote {target} with {len(values)} variables from {source}."]
    if overridden:
        text.append(f"From {FDE_SECRET_ID} instead of {SECRET_ID}: " + ", ".join(overridden))
    if added:
        text.append("Added: " + ", ".join(added))
    if kept_names:
        text.append("Kept local-only: " + ", ".join(kept_names))
    # Names only, never values.
    return Result(data={"path": str(target), "variables": sorted(values), "added": added,
                        "kept_local_only": kept_names, "sources": sources, "fde_overrides": overridden},
                  text="\n".join(text))


def login(ctx: Context) -> Result:
    if not shutil.which('aws'):
        raise DependencyMissing('aws', 'install the AWS CLI v2 (`mise install`)')
    ensure_profile(ctx.args.profile)
    subprocess.run(["aws", "sso", "login", "--profile", ctx.args.profile], check=True)
    return Result(data={"profile": ctx.args.profile},
                  text=f"Signed in as {ctx.args.profile}. Set AWS_PROFILE={ctx.args.profile} to use it; "
                       "logging in does not change the shell's AWS_PROFILE.")


def register(commands, common) -> None:
    # Both run off the tailnet: they are how a new machine gets the key that joins it.
    env = group(commands, "env", "The ignored repository .env built from gradiated/dev/env")
    parser = leaf(env, "build", build, Meta(
        "Write .env (mode 0600) from gradiated/dev/env, keeping local-only variables; prints names, never values",
        effects="write", repo=True, tailnet=False, interactive=True, requires=("aws",)), common)
    parser.add_argument("--profile", default="gradiated-restricted", help="AWS profile that reads the secret")
    parser.add_argument("--with-fde", action="store_true",
                        help="Also read gradiated/dev/fde (forward-deployed engineering keys); its values win")
    aws = group(commands, "aws", "Gradiated AWS access")
    parser = leaf(aws, "login", login, Meta(
        "Sign in to AWS SSO, creating the profile if it is missing (opens a browser)",
        effects="write", tailnet=False, interactive=True, requires=("aws",)), common)
    parser.add_argument("--profile", default="gradiated-readonly",
                        help="gradiated-readonly (default), gradiated-developer for writes, "
                             "gradiated-admin for break-glass")
