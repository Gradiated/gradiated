"""`gradctl repos`: list and clone a customer organization's GitHub repositories.

A customer grants access during post-training onboarding by installing the
Gradiated GitHub app; the installation is recorded in the product database.
These commands look the installation up, mint a one-hour installation token
with the app's private key, and list or clone what the customer selected.

Access is AWS's to grant: the app keys and the read-only database login live in
Secrets Manager outside gradiated/dev/, so the restricted level cannot read
them and readonly and above can.

- prod: the database through the tailnet as the read-only metabase_reader role
  (gradiated/prod/analytics/metabase-postgres), and the production app's key
  (gradiated/github-app/prod).
- dev: the local database (DATABASE_URL, default the docker-compose one) and the
  Gradiated [DEV] app's key (gradiated/github-app/dev).

Tokens are never printed or written to disk: git receives one as a header for
the clone only, so the cloned remote URL carries no credential.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from .core import CliError, Context, DependencyMissing, Meta, Result, UsageError, group, leaf

REGION = 'us-east-1'
LOCAL_DATABASE_URL = 'postgresql://gradiated:gradiated@127.0.0.1:5432/gradiated'
APP_SECRETS = {'prod': 'gradiated/github-app/prod', 'dev': 'gradiated/github-app/dev'}
PROD_DATABASE_SECRET = 'gradiated/prod/analytics/metabase-postgres'
GITHUB_API = 'https://api.github.com'
UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)

# One row per organization; installations are the active GitHub integrations.
QUERY = """\
select json_build_object(
  'id', o.id, 'name', o.name, 'slug', o.slug,
  'installations', coalesce((
    select json_agg(json_build_object('id', i.external_id::bigint,
                                      'account', i.settings ->> 'account_login')
                    order by i.created_at)
    from integrations i
    where i.organization_id = o.id and i.provider = 'github' and i.status = 'active'
  ), '[]'::json))
from organizations o
where o.id::text = :'organization' or o.slug = :'organization';
"""


def need(tool: str, hint: str) -> None:
    if not shutil.which(tool):
        raise DependencyMissing(tool, hint)


def aws_secret(secret_id: str) -> dict:
    need('aws', 'install it with `mise install`')
    profile = os.environ.get('AWS_PROFILE', 'gradiated-readonly')
    result = subprocess.run(['aws', '--profile', profile, '--region', REGION, 'secretsmanager',
                             'get-secret-value', '--secret-id', secret_id, '--query', 'SecretString',
                             '--output', 'text'], text=True, capture_output=True, timeout=60)
    if result.returncode != 0:
        denied = 'AccessDenied' in result.stderr
        raise CliError(
            f'could not read {secret_id} with the {profile} profile', 'access_denied' if denied else 'credentials_missing',
            'this needs the readonly level or above; ask for it in infra/bootstrap/identity-center/people.tf'
            if denied else 'run `gradctl aws login`, then retry')
    return json.loads(result.stdout)


def database_query(environment: str, organization: str) -> dict | None:
    need('psql', 'install it with `mise install` (mise pins the PostgreSQL client)')
    env = {**os.environ, 'PGOPTIONS': '-c default_transaction_read_only=on', 'PGCONNECT_TIMEOUT': '10'}
    if environment == 'prod':
        login = aws_secret(PROD_DATABASE_SECRET)
        env.update(PGHOST=login['host'], PGPORT=str(login['port']), PGDATABASE=login['database'],
                   PGUSER=login['username'], PGPASSWORD=login['password'], PGSSLMODE='require')
        target: list[str] = []
    else:
        target = ['--dbname', os.environ.get('DATABASE_URL') or LOCAL_DATABASE_URL]
    result = subprocess.run(['psql', *target, '-X', '-q', '-A', '-t', '-v', 'ON_ERROR_STOP=1',
                             '-v', f'organization={organization}', '-f', '-'],
                            input=QUERY, text=True, capture_output=True, env=env, timeout=60)
    if result.returncode != 0:
        raise CliError(f'the {environment} database query failed: {result.stderr.strip()[:300]}', 'database_failed',
                       'for prod, check `gradctl tailnet status`; for dev, start the local stack')
    row = result.stdout.strip()
    return json.loads(row) if row else None


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def app_jwt(app_id: str, private_key: str) -> str:
    """An RS256 app JWT, signed by openssl so gradctl needs no crypto package."""
    need('openssl', 'install OpenSSL; macOS and Linux include it')
    now = int(time.time())
    signing = (b64url(json.dumps({'alg': 'RS256', 'typ': 'JWT'}).encode()) + '.'
               + b64url(json.dumps({'iat': now - 60, 'exp': now + 540, 'iss': str(app_id)}).encode()))
    with tempfile.TemporaryDirectory() as directory:
        key = Path(directory, 'app.pem')
        key.touch(mode=0o600)
        key.write_text(private_key)
        result = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(key)], input=signing.encode(),
                                capture_output=True, timeout=30)
    if result.returncode != 0:
        raise CliError('could not sign the GitHub app JWT; the stored private key may be invalid', 'credentials_invalid')
    return signing + '.' + b64url(result.stdout)


def github(path: str, token: str, method: str = 'GET') -> dict:
    request = urllib.request.Request(GITHUB_API + path, method=method, headers={
        'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'gradctl'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise CliError(f'GitHub {method} {path.split("?")[0]} returned {error.code}', f'github_{error.code}') from None


def installation_repositories(jwt: str, installation: dict) -> dict:
    """The installation's repositories, or why it can no longer be read."""
    try:
        token = github(f"/app/installations/{installation['id']}/access_tokens", jwt, 'POST')['token']
    except CliError as error:
        if error.code == 'github_404':
            return {**installation, 'error': 'no longer installed', 'repositories': []}
        raise
    repositories, page = [], 1
    while True:
        batch = github(f'/installation/repositories?per_page=100&page={page}', token)['repositories']
        repositories += [{'full_name': r['full_name'], 'private': r['private'], 'default_branch': r['default_branch']}
                         for r in batch]
        if len(batch) < 100:
            break
        page += 1
    return {**installation, 'repositories': repositories, '_token': token}


def app_credentials(environment: str) -> tuple[str, str]:
    """The app ID and private key: GITHUB_APP_ID with GITHUB_APP_PRIVATE_KEY_PATH
    (a downloaded .pem) override the stored secret, for example before it exists."""
    path = os.environ.get('GITHUB_APP_PRIVATE_KEY_PATH')
    if path and os.environ.get('GITHUB_APP_ID'):
        return os.environ['GITHUB_APP_ID'], Path(path).expanduser().read_text()
    app = aws_secret(APP_SECRETS[environment])
    return app['GITHUB_APP_ID'], app['GITHUB_APP_PRIVATE_KEY']


def lookup(ctx: Context) -> dict:
    organization = ctx.args.organization.strip()
    if not (UUID.match(organization) or re.fullmatch(r'[a-z0-9][a-z0-9-]{0,38}', organization)):
        raise UsageError('--organization takes an organization ID or slug')
    environment = ctx.args.environment
    record = database_query(environment, organization)
    if not record:
        raise CliError(f'no {environment} organization has the ID or slug {organization}', 'not_found')
    if not record['installations']:
        raise CliError(f"{record['name']} has not installed the GitHub app", 'not_installed',
                       'the customer installs it during post-training onboarding')
    jwt = app_jwt(*app_credentials(environment))
    record['installations'] = [installation_repositories(jwt, item) for item in record['installations']]
    return record


def public(record: dict) -> dict:
    return {**record, 'installations': [{k: v for k, v in item.items() if k != '_token'}
                                        for item in record['installations']]}


def list_command(ctx: Context) -> Result:
    record = lookup(ctx)
    lines = [f"{record['name']} ({record['slug']})"]
    for item in record['installations']:
        lines.append(f"  {item['account']} (installation {item['id']})"
                     + (f": {item['error']}" if item.get('error') else ''))
        lines += [f"    {repo['full_name']}" for repo in item['repositories']]
    return Result(data=public(record), text='\n'.join(lines))


def clone_command(ctx: Context) -> Result:
    need('git', 'install git')
    record = lookup(ctx)
    into = Path(ctx.args.into or record['slug']).expanduser().resolve()
    wanted = {name.lower() for name in ctx.args.repo or []}
    cloned, skipped = [], []
    for item in record['installations']:
        if item.get('error'):
            continue
        header = 'AUTHORIZATION: basic ' + base64.b64encode(f"x-access-token:{item['_token']}".encode()).decode()
        for repo in item['repositories']:
            name = repo['full_name']
            if wanted and name.lower() not in wanted and name.split('/')[1].lower() not in wanted:
                continue
            target = into / name
            if target.exists():
                skipped.append({'repository': name, 'path': str(target), 'reason': 'already exists'})
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            ctx.log(f'cloning {name} into {target}')
            # The header applies to this clone only; nothing is stored in .git/config.
            result = subprocess.run(['git', '-c', 'credential.helper=', '-c', f'http.https://github.com/.extraheader={header}',
                                     'clone', '--quiet', f'https://github.com/{name}.git', str(target)],
                                    capture_output=True, text=True)
            if result.returncode != 0:
                raise CliError(f'git clone {name} failed: {result.stderr.strip()[:300]}', 'clone_failed',
                               data={'cloned': cloned, 'skipped': skipped})
            cloned.append({'repository': name, 'path': str(target)})
    if wanted and not cloned and not skipped:
        raise CliError('none of the --repo names is shared by this organization', 'not_found',
                       f"run `gradctl repos list --organization {record['slug']}`")
    text = '\n'.join([f"cloned {c['repository']} -> {c['path']}" for c in cloned]
                     + [f"skipped {s['repository']}: {s['reason']}" for s in skipped]) or 'nothing to clone'
    return Result(data={'organization': {k: record[k] for k in ('id', 'name', 'slug')}, 'cloned': cloned,
                        'skipped': skipped}, text=text)


def register(commands, common) -> None:
    repos = group(commands, 'repos', "List and clone a customer organization's GitHub repositories")
    requires = ('aws', 'psql', 'openssl')
    for name, run, meta in (
            ('list', list_command, Meta("List the repositories an organization shared through the GitHub app",
                                        requires=requires)),
            ('clone', clone_command, Meta("Clone the repositories an organization shared through the GitHub app",
                                          effects='write', requires=(*requires, 'git')))):
        sub = leaf(repos, name, run, meta, common)
        sub.add_argument('--organization', required=True, help='the organization ID or slug')
        sub.add_argument('--environment', choices=('prod', 'dev'), default='prod',
                         help='prod (default), or dev for the local database and the Gradiated [DEV] app')
        if name == 'clone':
            sub.add_argument('--into', help='directory to clone into (default ./<organization slug>)')
            sub.add_argument('--repo', action='append', help='only this repository, owner/name or name; repeatable')
