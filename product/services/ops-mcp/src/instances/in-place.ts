import type { RunSsh, SshTarget } from "./ssh.js";

const shellQuote = (value: string) => `'${value.replaceAll("'", "'\\''")}'`;

export const readEnrollment =
  "if test -f /etc/gradiated/in-place-enrollment.json; then cat /etc/gradiated/in-place-enrollment.json; else printf '{}'; fi";

export const bootstrapScript = String.raw`
import base64, json, os, pathlib, pwd, re, subprocess, sys, time
payload = json.load(sys.stdin)
env = payload["environment"]
uuid = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
for name in ("GRADIATED_INSTANCE_ID", "GRADIATED_NOMAD_NODE_ID", "GRADIATED_NOMAD_NODE_SECRET"):
    if not re.fullmatch(uuid, env[name]):
        sys.exit(64)
if not re.fullmatch(r"[a-z0-9-]{1,63}", env["GRADIATED_NODE_NAME"]):
    sys.exit(64)
for name in ("GRADIATED_RUNTIME_ACCESS_TOKEN", "GRADIATED_DEPLOYMENT_STATUS_TOKEN"):
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", env[name]):
        sys.exit(64)
base = pathlib.Path("/etc/gradiated/base-id").read_text().strip()
if not re.fullmatch(r"[a-zA-Z0-9._-]+", base):
    sys.exit(65)
for path in ("/etc/nomad/client.hcl", "/opt/gradiated/bin/start-client", "/opt/gradiated/bin/configure-serving"):
    if not pathlib.Path(path).is_file():
        sys.exit(65)
if pathlib.Path("/etc/nomad/node.hcl").exists() or subprocess.run(["pgrep", "-x", "nomad"], stdout=subprocess.DEVNULL).returncode == 0:
    sys.exit(73)
decoded = {name: base64.b64decode(env[name], validate=True) for name in ("GRADIATED_NOMAD_CA", "GRADIATED_NOMAD_CERT", "GRADIATED_NOMAD_KEY", "GRADIATED_ARTIFACT_ENV")}
def write(path, content, user):
    account = pwd.getpwnam(user)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as file:
        os.fchmod(file.fileno(), 0o600)
        os.fchown(file.fileno(), account.pw_uid, account.pw_gid)
        file.write(content)
os.umask(0o077)
for name, path, user in (
    ("GRADIATED_NOMAD_CA", "/etc/nomad/tls/ca.pem", "nomad"),
    ("GRADIATED_NOMAD_CERT", "/etc/nomad/tls/client.pem", "nomad"),
    ("GRADIATED_NOMAD_KEY", "/etc/nomad/tls/client-key.pem", "nomad"),
    ("GRADIATED_ARTIFACT_ENV", "/etc/gradiated/artifact.env", "downloader"),
):
    write(path, decoded[name], user)
client_dir = pathlib.Path("/var/lib/nomad/client")
client_dir.mkdir(parents=True, exist_ok=True)
account = pwd.getpwnam("nomad")
os.chmod(client_dir, 0o700)
os.chown(client_dir, account.pw_uid, account.pw_gid)
write(str(client_dir / "client-id"), env["GRADIATED_NOMAD_NODE_ID"].encode(), "nomad")
write(str(client_dir / "secret-id"), env["GRADIATED_NOMAD_NODE_SECRET"].encode(), "nomad")
serving_env = {**os.environ, **{name: env[name] for name in ("GRADIATED_RUNTIME_ACCESS_TOKEN", "GRADIATED_DEPLOYMENT_STATUS_TOKEN")}}
subprocess.run(["bash", "/opt/gradiated/bin/configure-serving"], env=serving_env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
name, instance = env["GRADIATED_NODE_NAME"], env["GRADIATED_INSTANCE_ID"]
config = f'name = "{name}"\nclient {{\n meta {{\n gradiated_instance_id = "{instance}"\n serving_ingress = "host-proxy"\n runtime_base_id = "{base}"\n }}\n}}\n'
write("/etc/nomad/node.hcl", config.encode(), "nomad")
identity = {name: env[name] for name in ("GRADIATED_INSTANCE_ID", "GRADIATED_NOMAD_NODE_ID", "GRADIATED_NOMAD_NODE_SECRET")}
write("/etc/gradiated/in-place-enrollment.json", json.dumps(identity).encode(), "root")
with open("/var/log/gradiated-nomad-client.log", "ab", buffering=0) as log:
    process = subprocess.Popen(["bash", "/opt/gradiated/bin/start-client"], stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
time.sleep(2)
if process.poll() is not None:
    sys.exit(70)
`;

export const installInPlace = async (
  run: RunSsh,
  target: SshTarget,
  environment: Readonly<Record<string, string>>,
) => {
  await run(
    target,
    `python3 -c ${shellQuote(bootstrapScript)}`,
    JSON.stringify({ environment }),
  );
};
