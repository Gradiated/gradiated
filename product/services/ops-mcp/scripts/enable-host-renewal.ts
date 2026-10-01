import { readFile } from "node:fs/promises";
import { parseArgs } from "node:util";
import { z } from "zod";
import {
  createControlDatabase,
  createInstanceCertificateService,
} from "@gradiated/control";
import { sshRunner } from "../src/instances/ssh.js";

const { values } = parseArgs({
  options: {
    host: { type: "string" },
    port: { type: "string", default: "22" },
    "host-key-sha256": { type: "string" },
    "private-key-file": { type: "string" },
    "instance-id": { type: "string" },
    "node-id": { type: "string" },
    revoke: { type: "boolean", default: false },
  },
});
const instanceId = z.uuid().parse(values["instance-id"]);
const database = createControlDatabase(
  z.string().min(1).parse(process.env.DATABASE_URL),
  1,
);
const credentials = createInstanceCertificateService(database.database);
const quote = (value: string) => `'${value.replaceAll("'", "'\\''")}'`;
const check = String.raw`
import json,pathlib,re,subprocess
p=pathlib.Path
subprocess.run(["openssl","version"],check=True,stdout=subprocess.DEVNULL)
print(json.dumps({"node":p("/var/lib/nomad/client/client-id").read_text().strip(),"instance":re.search(r'gradiated_instance_id\s*=\s*"([^"]+)"',p("/etc/nomad/node.hcl").read_text()).group(1)}))
`;
const install = String.raw`
import json,os,pathlib,pwd,re,subprocess,sys
payload=json.load(sys.stdin)
p=pathlib.Path
node=p("/var/lib/nomad/client/client-id").read_text().strip()
instance=re.search(r'gradiated_instance_id\s*=\s*"([^"]+)"',p("/etc/nomad/node.hcl").read_text()).group(1)
config=payload["config"]
if node != config["nomad_node_id"] or instance != config["instance_id"]:
    sys.exit(64)
account=pwd.getpwnam("nomad")
pids=[]
for candidate in p("/proc").glob("[0-9]*"):
    try:
        command=(candidate/"cmdline").read_bytes().split(b"\0")
        if p(os.fsdecode(command[0])).name == "nomad" and b"agent" in command and candidate.stat().st_uid == account.pw_uid:
            pids.append(candidate.name)
    except (OSError,IndexError):
        pass
if len(pids) != 1:
    sys.exit(65)
os.umask(0o077)
def write(path,content,mode,uid,gid):
    temporary=path+".renewal-install"
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,"w") as file:
        os.fchmod(file.fileno(),mode)
        os.fchown(file.fileno(),uid,gid)
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary,path)
write("/opt/gradiated/bin/renew-certificate",payload["script"],0o755,0,0)
write("/opt/gradiated/bin/run-renewer",payload["supervisor"],0o755,0,0)
subprocess.run(["python3","-m","py_compile","/opt/gradiated/bin/renew-certificate"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
write("/etc/nomad/tls/renewal.json",json.dumps(config),0o600,account.pw_uid,account.pw_gid)
write("/var/lib/nomad/client/agent.pid",pids[0]+"\n",0o600,account.pw_uid,account.pw_gid)
start="/opt/gradiated/bin/start-client"
backup=start+".before-renewal"
if not p(backup).exists():
    write(backup,p(start).read_text(),0o600,0,0)
write(start,payload["start_client"],0o755,0,0)
command=["setpriv","--reuid=nomad","--regid=nomad","--clear-groups","--inh-caps=-all","--ambient-caps=-all","--no-new-privs","bash","/opt/gradiated/bin/run-renewer"]
with open("/var/log/gradiated-certificate-renewal.log","ab",buffering=0) as log:
    subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
`;

try {
  if (values.revoke) {
    await credentials.revoke(instanceId);
    console.log(
      "Renewal authorization revoked. Existing certificates and connections remain valid.",
    );
  } else {
    const nodeId = z.uuid().parse(values["node-id"]);
    const target = {
      host: z.string().min(1).parse(values.host),
      port: z.coerce.number().int().min(1).max(65535).parse(values.port),
      hostKeySha256: z
        .string()
        .regex(/^[a-f0-9]{64}$/)
        .parse(values["host-key-sha256"]),
    };
    const run = sshRunner(
      await readFile(
        z.string().min(1).parse(values["private-key-file"]),
        "utf8",
      ),
    );
    let identity: { node: string; instance: string };
    try {
      identity = z
        .object({ node: z.uuid(), instance: z.uuid() })
        .parse(JSON.parse(await run(target, `python3 -c ${quote(check)}`)));
    } catch {
      throw new Error("Cannot verify host enrollment identity");
    }
    if (identity.node !== nodeId || identity.instance !== instanceId)
      throw new Error("Host identity does not match enrollment");

    const [script, startClient, supervisor] = await Promise.all([
      readFile(
        new URL(
          "../../../inference/images/nomad-base/renew-certificate.py",
          import.meta.url,
        ),
        "utf8",
      ),
      readFile(
        new URL(
          "../../../inference/images/nomad-base/start-client.sh",
          import.meta.url,
        ),
        "utf8",
      ),
      readFile(
        new URL(
          "../../../inference/images/nomad-base/run-renewer.sh",
          import.meta.url,
        ),
        "utf8",
      ),
    ]);
    const token = await credentials.enroll(instanceId, nodeId);
    await run(
      target,
      `python3 -c ${quote(install)}`,
      JSON.stringify({
        config: { instance_id: instanceId, nomad_node_id: nodeId, token },
        script,
        start_client: startClient,
        supervisor,
      }),
    );
    console.log(
      "Renewal agent installed without restarting Nomad. Verify its heartbeat, expiry and readiness before migrating another host.",
    );
  }
} finally {
  await database.pool.end();
}
