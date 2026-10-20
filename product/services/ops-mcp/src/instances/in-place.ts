import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { z } from "zod";
import type { RunSsh, SshTarget } from "./ssh.js";
import type { GpuInventory } from "./provider.js";

const shellQuote = (value: string) => `'${value.replaceAll("'", "'\\''")}'`;
const source = (name: string) =>
  readFile(new URL(`../../../../inference/${name}`, import.meta.url), "utf8");
const assets = {
  "/etc/gradiated/base-id": "images/gpu-base/base-id",
};

export const readEnrollment =
  'python3 -c \'import json,pathlib; p=pathlib.Path("/etc/gradiated/kubelet.json"); print(json.dumps({"GRADIATED_INSTANCE_ID":json.loads(p.read_text())["instance_id"]}) if p.exists() else "{}")\'';

export const verifyInstalledBase = String.raw`
import hashlib,json,pathlib,sys
files=json.load(sys.stdin)["files"]
for name,digest in files.items():
    if hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest()!=digest:
        raise ValueError("GPU base image differs from the pinned enrollment implementation")
print("qualified")
`;

export const verifyInPlaceBase = async (
  run: RunSsh,
  target: SshTarget,
  _image: string,
) => {
  const files = Object.fromEntries(
    await Promise.all(
      Object.entries(assets).map(async ([path, name]) => [
        path,
        createHash("sha256")
          .update(await source(name))
          .digest("hex"),
      ]),
    ),
  );
  await run(
    target,
    `python3 -c ${shellQuote(verifyInstalledBase)}`,
    JSON.stringify({ files }),
  );
};

export const bootstrapScript = String.raw`
import base64,contextlib,importlib.util,io,json,os,pathlib,subprocess,sys,time,urllib.request
sys.dont_write_bytecode=True
def enroll_quietly(module,bootstrap):
    output=os.dup(1)
    try:
        os.dup2(2,1)
        with contextlib.redirect_stdout(io.StringIO()):module.enroll(bootstrap)
    finally:
        os.dup2(output,1)
        os.close(output)
payload=json.load(sys.stdin)
config=pathlib.Path("/etc/gradiated/kubelet.json")
bootstrap=json.loads(base64.b64decode(payload["environment"]["GRADIATED_GPU_BOOTSTRAP"]))
if config.exists():
    current=json.loads(config.read_text())
    if current["instance_id"]!=bootstrap["instance_id"] or pathlib.Path(current["token_file"]).read_text()!=bootstrap["management_token"]:
        raise ValueError("Existing GPU enrollment differs; rotate credentials separately")
else:
    if subprocess.check_output(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader"],text=True).strip():
        raise ValueError("GPU workloads must drain before enrollment")
    pathlib.Path("/opt/gradiated/kubelet/launch-ready").unlink(missing_ok=True)
    bootstrap_path=pathlib.Path("/opt/gradiated/kubelet/bootstrap.py")
    if bootstrap.get("host_bundle"):
        import types
        for name in ("host_state", "host_bundle", "supervise", "install_seed"):
            module=types.ModuleType(name)
            module.__file__="/opt/gradiated/kubelet/"+name+".py"
            sys.modules[name]=module
            exec(compile(payload["installer"][name],module.__file__,"exec"),module.__dict__)
        bootstrap_path=sys.modules["install_seed"].install(bootstrap["host_bundle"])
    spec=importlib.util.spec_from_file_location("gpu_bootstrap",bootstrap_path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    try:enroll_quietly(module,bootstrap)
    except Exception:
        config.unlink(missing_ok=True)
        raise
pathlib.Path("/opt/gradiated/kubelet/launch-ready").touch(mode=0o600)
root=pathlib.Path("/var/lib/gradiated-kubelet")
def supervisor_alive():
    try:
        owner=json.loads((root/"supervisor.json").read_text())
        state=pathlib.Path(f"/proc/{owner['pid']}/stat").read_text().rsplit(")",1)[1].split()
        return state[0]!="Z" and state[19]==owner["birth"]
    except (OSError,ValueError,KeyError,IndexError):return False
if not pathlib.Path("/run/gradiated/host-init").exists() and not supervisor_alive():
    with open("/var/log/gradiated-kubelet-bootstrap.log","ab") as log:
        subprocess.Popen(["python3","-B","/opt/gradiated/kubelet/bootstrap.py"],env={"PATH":"/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
deadline=time.monotonic()+120
while True:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8889/healthz",timeout=5) as result:
            if result.status==200:
                root=pathlib.Path("/var/lib/gradiated-kubelet")
                owner=json.loads((root/"supervisor.json").read_text())
                birth=pathlib.Path(f"/proc/{owner['pid']}/stat").read_text().rsplit(")",1)[1].split()[19]
                if birth!=owner["birth"]:raise ValueError("GPU supervisor identity changed")
                epoch=max(1,json.loads((root/"fence.json").read_text())["epoch"]) if (root/"fence.json").exists() else 1
                request=urllib.request.Request("http://127.0.0.1:8887/_kubelet",data=json.dumps({"operation":"ping","epoch":epoch}).encode(),headers={"Authorization":"Bearer "+bootstrap["management_token"],"Content-Type":"application/json"})
                with urllib.request.urlopen(request,timeout=5) as response:
                    if response.status==200:break
    except (OSError,ValueError,KeyError):pass
    if time.monotonic()>deadline:raise ValueError("GPU host proxy is not ready")
    time.sleep(2)
status=json.loads(subprocess.check_output(["/opt/gradiated/tailscale/tailscale","--socket=/var/lib/gradiated-tailscale/socket","status","--json"],text=True))
tags=status["Self"].get("Tags",[])
promotion=pathlib.Path("/var/lib/gradiated-tailscale/reauth").exists() and "tag:gpu-bootstrap" in tags
if status["BackendState"]!="Running" or not ("tag:gpu-inference" in tags or promotion):raise ValueError("Private GPU identity is not ready")
root=pathlib.Path("/sys/fs/cgroup")
quota=(root/"cpu.max").read_text().split();cpu=os.cpu_count() if quota[0]=="max" else int(quota[0])//int(quota[1])
limit=(root/"memory.max").read_text().strip()
if limit=="max":limit=int(next(line.split()[1] for line in pathlib.Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemTotal:")))*1024
memory=max(1,int(limit)//(1024**3)-16)
gpus=subprocess.check_output(["nvidia-smi","--query-gpu=name","--format=csv,noheader"],text=True).splitlines()
if not gpus or len(set(gpus))!=1 or not any(product in gpus[0] for product in ("B300","RTX PRO 6000")):raise ValueError("A homogeneous GPU inventory is required")
if promotion:
    supervisors=[]
    for path in pathlib.Path("/proc").glob("[0-9]*"):
        try:
            args=(path/"cmdline").read_bytes().split(bytes(1))
            if len(args)>1 and os.path.basename(args[0])==b"bash" and args[1]==b"/opt/gradiated/bin/run-tailscale" and path.stat().st_uid==0:supervisors.append(int(path.name))
        except (OSError,ValueError):pass
    if len(supervisors)!=1:raise ValueError("Expected one root Tailscale supervisor")
    subprocess.Popen(["/bin/sh","-c",f"sleep 10; kill -USR1 {supervisors[0]}"],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
print(json.dumps({"tailscaleIp":next(ip for ip in status["TailscaleIPs"] if "." in ip),"gpuCount":len(gpus),"gpuProduct": "B300" if "B300" in gpus[0] else "RTX-PRO-6000", "cpu":max(1,int(cpu*0.9)),"memoryGiB":memory,"promotion":promotion}))
`;

export const inventorySchema = z.object({
  tailscaleIp: z.ipv4().refine((ip) => {
    const [a, b] = ip.split(".").map(Number);
    return a === 100 && b! >= 64 && b! <= 127;
  }),
  gpuCount: z.number().int().positive(),
  gpuProduct: z.enum(["B300", "RTX-PRO-6000"]),
  cpu: z.number().int().positive(),
  memoryGiB: z.number().int().positive(),
  promotion: z.boolean().optional(),
});

export const installInPlace = async (
  run: RunSsh,
  target: SshTarget,
  environment: Readonly<Record<string, string>>,
): Promise<GpuInventory & { promotion?: boolean }> => {
  const result = await run(
    target,
    `python3 -c ${shellQuote(bootstrapScript)}`,
    JSON.stringify({
      environment,
      installer: Object.fromEntries(
        await Promise.all(
          ["host_state", "host_bundle", "supervise", "install_seed"].map(
            async (name) => [
              name,
              await source(
                `gpu/${name === "install_seed" ? "install-seed" : name}.py`,
              ),
            ],
          ),
        ),
      ),
    }),
    30 * 60 * 1000,
  );
  return inventorySchema.parse(JSON.parse(result));
};
