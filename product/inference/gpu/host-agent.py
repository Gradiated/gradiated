#!/usr/bin/env python3
import fcntl
from contextlib import ExitStack, contextmanager
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import pwd
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_state import atomic_json, bound_log, sync_directory

REQUEST_DRAIN_SECONDS = 660

ROOT = Path("/var/lib/gradiated-kubelet")
CONFIG = Path("/etc/gradiated/kubelet.json")
PROCESS_SCOPE = {"boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                 "pid_namespace": os.readlink("/proc/self/ns/pid")}
CGROUP = Path("/sys/fs/cgroup")


@contextmanager
def configuration_lock(root):
    fd = os.open(root / 'config.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def prepare_cgroups():
    required = {"cpu", "memory", "pids"}
    if not required.issubset(set((CGROUP / "cgroup.controllers").read_text().split())):
        raise RuntimeError("CPU, memory and process limits are required")
    if not required.issubset(set((CGROUP / "cgroup.subtree_control").read_text().split())):
        system = CGROUP / "gradiated-system"
        system.mkdir(exist_ok=True)
        for pid in (CGROUP / "cgroup.procs").read_text().split():
            try:
                (system / "cgroup.procs").write_text(pid)
            except ProcessLookupError:
                pass
        (CGROUP / "cgroup.subtree_control").write_text("+cpu +memory +pids")
    pods = CGROUP / "gradiated-pods"
    pods.mkdir(exist_ok=True)
    (pods / "cgroup.subtree_control").write_text("+cpu +memory +pids")


def pod_cgroup(uid):
    return CGROUP / "gradiated-pods" / str(uuid.UUID(uid))


def process_birth(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return None if fields[0] == "Z" else fields[19]
    except FileNotFoundError:
        return None


def alive(owner):
    return bool(owner and owner["birth"] and all(owner.get(key, value) == value for key, value in PROCESS_SCOPE.items())
                and process_birth(owner["pid"]) == owner["birth"])


def owner(process):
    return {"pid": process.pid, "birth": process_birth(process.pid), **PROCESS_SCOPE}


def owned_signal(process, signum):
    if alive(process):
        os.killpg(process["pid"], signum)


def health(port, path="/health"):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def spawn_user(user, command, environment, log_path):
    with log_path.open("ab") as output:
        return subprocess.Popen(
            ["/usr/bin/setpriv", f"--reuid={user}", f"--regid={user}", "--init-groups",
             "--inh-caps=-all", "--ambient-caps=-all", "--no-new-privs", "--pdeathsig=TERM", *command],
            env=environment, stdin=subprocess.DEVNULL, stdout=output,
            stderr=subprocess.STDOUT, start_new_session=True, cwd="/",
        )


def gpu_pool(config):
    return config.get("gpu_uuids") or [config["gpu_uuid"]]


def runtime_profile(config, pod):
    image = pod["spec"]["containers"][0]["image"]
    digest = image.rsplit("@sha256:", 1)[-1]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("A pinned runtime bundle is required")
    profiles = config.get("runtimes")
    if profiles is None:
        profiles = {config["bundle_sha256"]: {
            "image": f"gradiated/kev-bundle@sha256:{config['bundle_sha256']}",
            "model_id": config["model_id"], "release": config["release"],
            "gpus": 1, "cpu": "16", "memory": "64Gi", "request_memory": "48Gi",
            "startup_timeout": 1800,
        }}
    profile = profiles.get(digest)
    if not profile or profile["image"] != image:
        raise ValueError("Unsupported runtime release")
    if profile.get("kind") == "training":
        recipe = json.loads(pod["metadata"].get("annotations", {}).get("gradiated.com/training-recipe", "{}"))
        if not isinstance(recipe, dict):
            raise ValueError("Training recipe must be an object")
        count = recipe.get("gpu_count", 1)
        if type(count) is not int or not 1 <= count <= 8:
            raise ValueError("Training GPU count must be between one and eight")
        profile = {**profile, "gpus": count, "cpu": str(4 * count), "memory": f"{64 * count}Gi", "recipe": recipe}
    allowed_environment = {"TENSOR_PARALLEL_SIZE", "MODEL_ID", "LORA_ENABLED", "LORA_BASE_MODEL_REVISION",
        "LORA_GPU_SLOTS", "LORA_CPU_SLOTS", "LORA_MAX_RANK", "LORA_DISK_CACHE_BYTES", "LORA_DOWNLOAD_HOSTS",
        "GRADIATED_API_BASE_URL", "HOST_IDENTITY_FILE"}
    extra = profile.get("environment", {})
    if set(extra) - allowed_environment or any(not isinstance(value, str) for value in extra.values()):
        raise ValueError("Unsupported runtime environment")
    if extra.get("GRADIATED_API_BASE_URL", "http://127.0.0.1:3004") != "http://127.0.0.1:3004":
        raise ValueError("GPU control traffic must use the private bridge")
    return digest, profile


HUB_API = "https://huggingface.co/api/models"
CACHE_MARKER = ".gradiated-last-used"
UNUSED_WEIGHT_FORMATS = (".bin", ".pt", ".pth", ".ckpt", ".gguf", ".h5", ".msgpack", ".onnx")


def hf_home(config, profile):
    return Path(profile.get("hf_home", config.get("hf_home", "/home/runtime/.cache/huggingface")))


def model_references(profile):
    if profile.get("kind") == "training":
        recipe = profile.get("recipe") or {}
        references = [(recipe.get("model"), recipe.get("revision"))]
    else:
        # Kev loads its base checkpoint from the tokenizer repository as well as its own weights.
        release = profile.get("release", {})
        references = [(release.get("model_path"), release.get("model_revision")),
                      (release.get("tokenizer_path"), release.get("tokenizer_revision"))]
    return [(repo, revision) for repo, revision in references
            if isinstance(repo, str) and re.fullmatch(r"[\w.-]+/[\w.-]+", repo)]


def model_repos(profile):
    # Protection needs only the repository; a pod with an unpinned revision still uses it.
    return list(dict.fromkeys(repo for repo, _ in model_references(profile)))


def model_weights(profile):
    return list(dict.fromkeys(
        (repo, revision) for repo, revision in model_references(profile)
        if isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision)))


def repo_directory(hub, repo):
    return hub / ("models--" + repo.replace("/", "--"))


def hub_files(repo, revision):
    with urllib.request.urlopen(f"{HUB_API}/{repo}/revision/{revision}?blobs=true", timeout=30) as response:
        files = {item["rfilename"]: item.get("size") or 0 for item in json.load(response)["siblings"]}
    # Loaders fetch safetensors and skip the other weight formats a repo may also publish.
    if any(name.endswith(".safetensors") for name in files):
        files = {name: size for name, size in files.items() if not name.endswith(UNUSED_WEIGHT_FORMATS)}
    return files


def missing_bytes(hub, repo, revision, files):
    snapshot = repo_directory(hub, repo) / "snapshots" / revision
    return sum(size for name, size in files.items() if not (snapshot / name).exists())


def last_used(path):
    try:
        return (path / CACHE_MARKER).stat().st_mtime
    except FileNotFoundError:
        return path.stat().st_mtime


def evict_models(hub, needed, protected, log, usage=shutil.disk_usage):
    free = usage(hub).free
    candidates = sorted((path for path in hub.glob("models--*") if path.is_dir() and path.name not in protected),
                        key=last_used)
    for path in candidates:
        if free >= needed:
            return
        shutil.rmtree(path)
        log(f"Evicted cached model {path.name}")
        free = usage(hub).free
    if free < needed:
        log(f"Model cache needs {needed} free bytes but only {free} remain after eviction")


def lora_headroom(profile, directory):
    environment = profile.get("environment", {})
    if environment.get("LORA_ENABLED") != "true":
        return 0
    cache = directory / "lora"
    used = sum(path.stat().st_size for path in cache.rglob("*")
               if path.is_file() and not path.is_symlink()) if cache.is_dir() else 0
    return max(0, int(environment.get("LORA_DISK_CACHE_BYTES", "0")) - used)


def prepare_model_cache(config, profile, directory, pods, log, files=hub_files, usage=shutil.disk_usage):
    hub = hf_home(config, profile) / "hub"
    weights = model_weights(profile)
    if not weights or not hub.is_dir():
        return
    # Every model on this host stays cached, and unfinished downloads and LoRA caches keep their space.
    pods = [(profile, directory), *pods]
    required = {pin for item, _ in pods for pin in model_weights(item)}
    protected = {repo_directory(hub, repo).name for item, _ in pods for repo in model_repos(item)}
    needed = config.get("model_cache_reserve_gib", 64) * 2**30
    needed += sum(lora_headroom(item, path) for item, path in pods)
    for repo, revision in required:
        try:
            needed += missing_bytes(hub, repo, revision, files(repo, revision))
        except (OSError, ValueError, KeyError) as error:
            log(f"Could not size {repo}@{revision}: {error}")
    with (hub.parent / ".gradiated-cache.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        evict_models(hub, needed, protected, log, usage)
        for repo, _ in weights:
            cached = repo_directory(hub, repo)
            if cached.is_dir():
                (cached / CACHE_MARKER).touch()


def host_pods(config, exclude):
    # A pod whose state cannot be read may still hold weights, so its error skips eviction.
    pods = []
    for path in (ROOT / "pods").glob("*/state.json"):
        if path.parent.name == exclude:
            continue
        try:
            state = json.loads(path.read_text())
        except FileNotFoundError:
            continue
        pods.append((runtime_profile(config, state["pod"])[1], path.parent))
    return pods


def task(uid, stopping):
    lock_path = ROOT / 'pods' / uid / 'task.lock'
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    lock = os.fdopen(fd, 'r+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    (pod_cgroup(uid) / "cgroup.procs").write_text(str(os.getpid()))
    directory = ROOT / "pods" / uid
    with configuration_lock(ROOT):
        config = json.loads(CONFIG.read_text())
        state = json.loads((directory / 'state.json').read_text())
        if state.get('draining'):
            return
        state['task'] = {'pid': os.getpid(), 'birth': process_birth(os.getpid()), **PROCESS_SCOPE}
        atomic_json(directory / 'state.json', state)
    digest, profile = runtime_profile(config, state["pod"])
    bundle = ROOT / "bundles" / digest
    if (bundle / ".bundle-sha256").read_text().strip() != digest:
        raise ValueError("Unverified runtime bundle")
    devices = state.get("gpu_uuids", gpu_pool(config)[:profile["gpus"]])
    base = state.get("port_base", 38080)
    environment = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": "/home/runtime", "HF_HOME": profile.get("hf_home", config.get("hf_home", "/home/runtime/.cache/huggingface")),
        "XDG_CACHE_HOME": "/home/runtime/.cache", "OMP_NUM_THREADS": profile["cpu"],
        "NVIDIA_VISIBLE_DEVICES": ",".join(devices), "CUDA_VISIBLE_DEVICES": ",".join(devices),
        "RUNTIME_HOST": "127.0.0.1", "RUNTIME_PORT": str(base),
        "ADAPTER_PORT": str(base + 2), "WARMUP_PORT": str(base + 3),
        "RUNTIME_STARTUP_TIMEOUT_SECONDS": str(profile["startup_timeout"]),
        "TORCHINDUCTOR_CACHE_DIR": "/home/runtime/.cache/torchinductor",
        "TRITON_CACHE_DIR": "/home/runtime/.cache/triton",
        "GRADIATED_RUNTIME_DIR": str(directory),
        **profile.get("environment", {}),
    }
    if profile.get("kind") == "training":
        environment.update({"GRADIATED_POD_UID": uid,
                            "GRADIATED_RUNTIME_ROOT": str(bundle), "TRAINER_IMAGE_DIGEST": digest})
        if profile["recipe"]:
            environment["TRAINING_RECIPE_JSON"] = json.dumps(profile["recipe"])
    with (directory / "runtime.log").open("a") as cache_log:
        def log(message):
            cache_log.write(f"model-cache: {message}\n")
        try:
            prepare_model_cache(config, profile, directory, host_pods(config, uid), log)
        except Exception as error:
            log(f"Skipped eviction: {error}")
    model = reporter = None
    try:
        with ExitStack() as stack:
            runtime_user = pwd.getpwnam("runtime")
            lock_directory = Path("/home/runtime/.cache/gradiated/gpu-locks")
            lock_directory.mkdir(parents=True, exist_ok=True)
            os.chown(lock_directory, runtime_user.pw_uid, runtime_user.pw_gid)
            for device in sorted(devices):
                lock_path = lock_directory / device
                gpu_lock = stack.enter_context(lock_path.open("a"))
                os.chown(lock_path, runtime_user.pw_uid, runtime_user.pw_gid)
                fcntl.flock(gpu_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            active = subprocess.run(
                ["nvidia-smi", f"--id={','.join(devices)}", "--query-compute-apps=pid", "--format=csv,noheader"],
                capture_output=True, text=True, check=True, timeout=10,
            ).stdout.strip()
            if active and active != "No running processes found":
                raise ValueError("GPU already has a compute process")
            model = spawn_user("runtime", [str(bundle / "runtime-launch"), str(bundle)],
                               environment, directory / "runtime.log")
            atomic_json(directory / "runtime.json", {"runtime": owner(model)})
            if profile.get("kind") != "training":
                reporting = {
                    "PATH": environment["PATH"], "DESMOND_DEPLOYMENT_ID": uid,
                    "DESMOND_RELEASE": profile["release"]["runtime_revision"],
                    "DESMOND_MODEL": profile["model_id"],
                    "DESMOND_MODEL_REVISION": profile["release"]["model_revision"],
                    "DESMOND_RUNTIME_HOST": "127.0.0.1",
                    "DESMOND_RUNTIME_PORT": str(base + 3 if profile.get("warmup") else base),
                    "DESMOND_INGRESS_PORT": "8889", "DESMOND_CONTROL_HOST": "127.0.0.1",
                    "DESMOND_CONTROL_PORT": str(base + 1), "DESMOND_STATUS_HOST": "127.0.0.1",
                    "DESMOND_STATUS_PORT": "3004",
                    "DESMOND_CONTROL_TOKEN_FILE": "/etc/gradiated/runtime-access.token",
                }
                reporter = spawn_user("desmond", ["/opt/gradiated/kubelet/desmondd", "--observe"],
                                      reporting, directory / "desmond.log")
                atomic_json(directory / "runtime.json", {
                    "runtime": owner(model), "reporter": owner(reporter), "started_at": time.time(),
                })
            while not stopping.wait(1):
                if model.poll() is not None or (reporter and reporter.poll() is not None):
                    raise RuntimeError("Runtime or reporter exited")
    finally:
        for process in (model, reporter):
            if process and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in (model, reporter):
            if process:
                try:
                    process.wait(timeout=65)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)


class RuntimeStaging(Exception):
    pass


class Agent:
    def __init__(self, config, root=ROOT, config_path=None):
        self.config, self.root = config, root
        self.config_path = config_path
        self.lock = threading.Lock()
        self.children = {}
        self.catalogue_task = None
        self.catalogue_wanted = {}
        self.catalogue_ready = False

    def states(self):
        return [json.loads(path.read_text()) for path in (self.root / "pods").glob("*/state.json")]

    def reap_children(self):
        for uid, process in list(self.children.items()):
            if process.poll() is not None:
                del self.children[uid]

    def ensure_task(self, state):
        if state.get('draining') or alive(state.get('task')):
            return
        _, profile = runtime_profile(self.config, state['pod'])
        if profile.get('kind') == 'training' and state.get('task'):
            return
        uid = state['pod']['metadata']['uid']
        directory = self.root / 'pods' / uid
        self.stop(directory, state)
        group = pod_cgroup(uid)
        if group.exists() and (group / 'cgroup.procs').read_text().strip():
            raise RuntimeError('Unrecorded pod processes retain their GPU claim')
        with (directory / 'task.log').open('ab') as output:
            process = subprocess.Popen([sys.executable, __file__, 'task', uid],
                env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'}, stdin=subprocess.DEVNULL,
                stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        self.children[uid] = process
        state['task'] = owner(process)
        atomic_json(directory / 'state.json', state)

    def housekeep(self, now=None):
        now = time.time() if now is None else now
        with self.lock, configuration_lock(self.root):
            if self.config_path is not None:
                self.config = json.loads(self.config_path.read_text())
            states = self.states()
            protected = set(self.config.get('runtimes', {})) | set(self.catalogue_wanted)
            if self.config.get('bundle_sha256'):
                protected.add(self.config['bundle_sha256'])
            protected.update(runtime_profile(self.config, state['pod'])[0] for state in states)
            retired = []
            unknown_processes = False
            for directory in (self.root / 'pods').iterdir():
                if directory.is_symlink() or not directory.is_dir():
                    continue
                uid = str(uuid.UUID(directory.name))
                group = pod_cgroup(uid)
                occupied = group.exists() and bool((group / 'cgroup.procs').read_text().strip())
                details_path = directory / 'runtime.json'
                details = json.loads(details_path.read_text()) if details_path.exists() else {}
                live = any(alive(details.get(key)) for key in ('runtime', 'reporter'))
                active = (directory / 'state.json').exists()
                if not active and (occupied or live):
                    unknown_processes = True
                if not active and not occupied and not live:
                    retired.append(directory)
                for path in directory.glob('*.log'):
                    bound_log(path)
            for index, directory in enumerate(sorted(retired, key=lambda path: path.stat().st_mtime, reverse=True)):
                age = now - directory.stat().st_mtime
                if index >= 20 or age > 7 * 86400:
                    shutil.rmtree(directory)
            if not unknown_processes:
                bundles = self.root / 'bundles'
                unused = [path for path in bundles.glob('*') if not path.is_symlink() and path.is_dir()
                          and re.fullmatch('[0-9a-f]{64}', path.name) and path.name not in protected
                          and (path / '.bundle-sha256').is_file() and not (path / '.bundle-sha256').is_symlink()
                          and (path / '.bundle-sha256').read_text().strip() == path.name]
                for index, path in enumerate(sorted(unused, key=lambda path: path.stat().st_mtime, reverse=True)):
                    if index >= 2:
                        shutil.rmtree(path)
            for path in self.root.glob('*.log'):
                bound_log(path)

    def proxy_config(self):
        proxy = self.root / "proxy"
        lines = [f"worker_processes 1; pid {proxy}/nginx.pid; error_log stderr warn;",
                 "events { worker_connections 2048; }", "http { access_log off; client_max_body_size 32M;",
                 f"client_body_temp_path {proxy}/body; proxy_temp_path {proxy}/temp;",
                 "server { listen 127.0.0.1:8889;",
                 f'proxy_http_version 1.1; proxy_set_header Connection ""; proxy_set_header Authorization ""; proxy_buffering off; proxy_request_buffering off; proxy_read_timeout {REQUEST_DRAIN_SECONDS}s;',
                 'location = /private-healthz { return 200 "ok\\n"; }',
                 'location = /healthz { return 200 "ok\\n"; }',
                 "location = /_kubelet { proxy_set_header Authorization $http_authorization; proxy_pass http://127.0.0.1:8887; }",
                 'location / { return 404 "unknown deployment\\n"; }',
                 'location ~ ^/alloc/[^/]+/v1/(load|unload)_lora_adapter$ { return 404; }']
        for state in self.states():
            uid = str(uuid.UUID(state["pod"]["metadata"]["uid"]))
            port = state.get("port_base", 38080)
            _, profile = runtime_profile(self.config, state["pod"])
            if state.get("draining"):
                lines.append(f"location = /alloc/{uid}/health {{ return 503; }}")
            elif profile.get("warmup"):
                lines.append(f"location = /alloc/{uid}/health {{ proxy_pass http://127.0.0.1:{port + 3}/health; }}")
            if profile.get("adapters"):
                lines.append(f"location /alloc/{uid}/internal/adapters {{ proxy_pass http://127.0.0.1:{port + 2}/internal/adapters; }}")
            lines.append(f"location /alloc/{uid}/ {{ proxy_pass http://127.0.0.1:{port}/; "
                         "proxy_http_version 1.1; proxy_set_header Connection \"\"; "
                         "proxy_set_header Authorization \"\"; proxy_buffering off; "
                         f"proxy_request_buffering off; proxy_read_timeout {REQUEST_DRAIN_SECONDS}s; }}")
        return "\n".join([*lines, "} }"])

    def refresh_proxy(self):
        path = self.root / "nginx.conf"
        temporary = path.with_suffix(".new")
        configuration = self.proxy_config()
        test_pid = self.root / "proxy" / "nginx-test.pid"
        temporary.write_text(configuration.replace(f"pid {self.root}/proxy/nginx.pid;", f"pid {test_pid};"))
        temporary.chmod(0o644)
        subprocess.run(["nginx", "-t", "-q", "-c", str(temporary)], check=True,
                       capture_output=True, timeout=10)
        test_pid.unlink(missing_ok=True)
        temporary.write_text(configuration)
        temporary.replace(path)
        pid_file = self.root / "proxy" / "nginx.pid"
        if pid_file.exists():
            value = pid_file.read_text().strip()
            if not value:
                account = pwd.getpwnam("desmond")
                matches = []
                for process in Path("/proc").glob("[0-9]*/cmdline"):
                    try:
                        command = process.read_bytes()
                        if process.stat().st_uid == account.pw_uid and b"nginx: master process" in command and str(path).encode() in command:
                            matches.append(int(process.parent.name))
                    except FileNotFoundError:
                        pass
                if len(matches) != 1:
                    if health(8889, "/healthz"):
                        raise RuntimeError("Cannot identify the private proxy")
                    pid_file.unlink()
                    return
                value = str(matches[0])
                pid_file.write_text(value)
                os.chown(pid_file, account.pw_uid, account.pw_gid)
            pid = int(value)
            command_path = Path(f"/proc/{pid}/cmdline")
            if not command_path.exists() or not process_birth(pid):
                pid_file.unlink()
                return
            command = command_path.read_bytes()
            if str(path).encode() not in command:
                raise RuntimeError("Proxy PID does not belong to this agent")
            os.kill(pid, signal.SIGHUP)

    def ensure_proxy(self):
        path = self.root / 'nginx.conf'
        if not path.exists() or path.read_text() != self.proxy_config():
            self.refresh_proxy()
        process = self.children.get("proxy")
        if process and process.poll() is None:
            return
        pid_file = self.root / "proxy" / "nginx.pid"
        if pid_file.exists():
            value = pid_file.read_text().strip()
            if value and process_birth(int(value)):
                command = Path(f"/proc/{int(value)}/cmdline").read_bytes()
                if str(self.root / "nginx.conf").encode() not in command:
                    raise RuntimeError("Proxy PID does not belong to this agent")
                return
            pid_file.unlink()
        group = CGROUP / "gradiated-proxy"
        group.mkdir(exist_ok=True)
        if (group / "cgroup.procs").read_text().strip():
            (group / "cgroup.kill").write_text("1")
            deadline = time.monotonic() + 5
            while (group / "cgroup.procs").read_text().strip() and time.monotonic() < deadline:
                time.sleep(.1)
            if (group / "cgroup.procs").read_text().strip():
                raise RuntimeError("Old private proxy processes did not stop")
        (group / "memory.max").write_text(str(256 * 1024 ** 2))
        (group / "pids.max").write_text("64")
        self.refresh_proxy()
        with (self.root / "proxy.log").open("ab") as output:
            self.children["proxy"] = subprocess.Popen(
                [sys.executable, __file__, "proxy"],
                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                start_new_session=True)

    def validate(self, pod):
        uid = str(uuid.UUID(pod["metadata"]["uid"]))
        spec = pod["spec"]
        if spec.get("nodeName") != f"gpu-{self.config['instance_id']}":
            raise ValueError("Pod is assigned to another host")
        containers = spec.get("containers", [])
        if len(containers) != 1:
            raise ValueError("One pinned runtime container is required")
        digest, profile = runtime_profile(self.config, pod)
        annotations = pod["metadata"].get("annotations", {})
        if (annotations.get("gradiated.com/workload-kind") == "training") != (profile.get("kind") == "training"):
            raise ValueError("Workload kind does not match its runtime")
        if annotations.get("gradiated.com/model-id") != profile["model_id"]:
            raise ValueError("Unsupported model")
        if json.loads(annotations.get("gradiated.com/release", "null")) != profile["release"]:
            raise ValueError("Runtime metadata does not match the pinned release")
        container = containers[0]
        if any(container.get(key) for key in ["env", "envFrom", "command", "args", "volumeMounts"]):
            raise ValueError("Runtime execution overrides are unsupported")
        resources = container.get("resources", {})
        for kind in ["limits", "requests"]:
            values = resources.get(kind, {})
            memory = profile.get("request_memory", profile["memory"]) if kind == "requests" else profile["memory"]
            if str(values.get("nvidia.com/gpu")) != str(profile["gpus"]) or values.get("cpu") != profile["cpu"] or values.get("memory") != memory:
                raise ValueError("Runtime resource accounting does not match its profile")
        if spec.get("volumes") or spec.get("initContainers") or spec.get("hostNetwork") or spec.get("hostPID"):
            raise ValueError("Unsupported pod execution feature")
        return uid

    def assignment(self, pod):
        _, profile = runtime_profile(self.config, pod)
        states = self.states()
        occupied = {gpu for state in states for gpu in state.get("gpu_uuids", gpu_pool(self.config)[:runtime_profile(self.config, state["pod"])[1]["gpus"]])}
        available = [gpu for gpu in gpu_pool(self.config) if gpu not in occupied]
        if len(available) < profile["gpus"]:
            raise ValueError("Required GPUs are owned by another deployment")
        ports = {state.get("port_base", 38080) for state in states}
        port = next((18080 + slot * 8 for slot in range(16) if 18080 + slot * 8 not in ports), None)
        if port is None:
            raise ValueError("No runtime port slot available")
        return available[:profile["gpus"]], port

    def stop(self, directory, state):
        owned_signal(state.get("task"), signal.SIGTERM)
        details_path = directory / "runtime.json"
        details = json.loads(details_path.read_text()) if details_path.exists() else {}
        processes = [state.get("task"), details.get("runtime"), details.get("reporter")]
        for process in processes:
            owned_signal(process, signal.SIGTERM)
        deadline = time.monotonic() + 75
        while any(alive(process) for process in processes) and time.monotonic() < deadline:
            time.sleep(1)
        for process in processes:
            owned_signal(process, signal.SIGKILL)
        deadline = time.monotonic() + 5
        while any(alive(process) for process in processes) and time.monotonic() < deadline:
            time.sleep(.1)
        if any(alive(process) for process in processes):
            raise RuntimeError("Host processes did not stop; GPU claim retained")

    def configure(self, catalogue, epoch):
        if not isinstance(catalogue, dict) or not catalogue:
            raise ValueError('A pinned runtime catalogue is required')
        wanted = {}
        for digest, profile in catalogue.items():
            if not re.fullmatch('[0-9a-f]{64}', digest) or not profile.get('image', '').endswith('@sha256:' + digest):
                raise ValueError('Invalid pinned runtime catalogue')
            if profile.get('environment', {}).get('HOST_IDENTITY_FILE'):
                raise ValueError('Legacy host credentials are not supported')
            if profile.get('kind') == 'training' or profile['gpus'] <= len(gpu_pool(self.config)):
                wanted[digest] = profile
        self.catalogue_wanted = wanted
        task = (epoch, json.dumps(wanted, sort_keys=True))
        active = {runtime_profile(self.config, state['pod'])[0] for state in self.states()}
        if self.catalogue_task == task and (not self.catalogue_ready or set(self.config.get('runtimes', {})) == set(wanted) | active):
            return {'configuring': not self.catalogue_ready}
        self.catalogue_task = task
        self.catalogue_ready = False

        def stage():
            try:
                log_path = self.root / 'bundle-download.log'
                fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'ab') as log:
                    for digest in wanted:
                        marker = self.root / 'bundles' / digest / '.bundle-sha256'
                        if marker.exists() and marker.read_text().strip() == digest:
                            continue
                        subprocess.run(['runuser', '-u', 'downloader', '--', '/opt/gradiated/bin/fetch-runtime',
                            f's3::https://gradiated-prod-model-artifacts-873716897517.s3.us-east-1.amazonaws.com/bundles/sha256/{digest}.tar.gz',
                            digest, str(self.root / 'bundles' / digest)], stdout=log, stderr=log, check=True, timeout=1800)
                with self.lock, configuration_lock(self.root):
                    if self.catalogue_task != task or json.loads((self.root / 'fence.json').read_text())['epoch'] != epoch:
                        return
                    current = json.loads(self.config_path.read_text()) if self.config_path is not None else self.config
                    merged = dict(wanted)
                    for state in self.states():
                        digest, profile = runtime_profile(current, state['pod'])
                        merged[digest] = current.get('runtimes', {}).get(digest, {**profile, 'image': state['pod']['spec']['containers'][0]['image']})
                    updated = {**current, 'gpu_uuids': gpu_pool(current), 'runtimes': merged}
                    if self.config_path is not None:
                        atomic_json(self.config_path, updated)
                    self.config = updated
                    self.catalogue_ready = True
            except Exception as error:
                with self.lock:
                    if self.catalogue_task == task:
                        self.catalogue_task = None
                print(f'Runtime catalogue staging failed: {type(error).__name__}', flush=True)
        threading.Thread(target=stage, daemon=True).start()
        return {'configuring': True}

    def request(self, body):
        with self.lock, configuration_lock(self.root):
            if self.config_path is not None:
                self.config = json.loads(self.config_path.read_text())
            fence_file = self.root / 'fence.json'
            fence = json.loads(fence_file.read_text()) if fence_file.exists() else {'epoch': 0}
            operation = body['operation']
            if operation == 'ping':
                return {'instance_id': self.config['instance_id'], 'epoch': fence['epoch']}
            if operation == 'fence':
                return {'epoch': fence['epoch']}
            if operation == 'claim':
                term = str(uuid.UUID(body['term']))
                if fence.get('term') == term:
                    sync_directory(self.root)
                    return {'epoch': fence['epoch']}
                if type(body.get('epoch')) is not int or body['epoch'] != fence['epoch']:
                    raise ValueError('Controller claim raced a newer generation')
                if not 0 <= fence['epoch'] < 2**63 - 1:
                    raise ValueError('Controller generation exhausted')
                fence = {'epoch': fence['epoch'] + 1, 'term': term}
                atomic_json(fence_file, fence)
                return {'epoch': fence['epoch']}
            epoch = body.get("epoch")
            if type(epoch) is not int or not 1 <= epoch <= 2**63 - 1:
                raise ValueError("Missing controller fencing epoch")
            previous = fence['epoch']
            # Existing reservations may use the lease-counter protocol until their first claim.
            if not fence.get('term') and previous > 0 and epoch > previous:
                atomic_json(fence_file, {'epoch': epoch})
                previous = epoch
            if fence.get('term') and body.get('term') != fence['term']:
                raise ValueError('Stale controller term')
            if epoch != previous:
                raise ValueError("Stale controller fencing epoch")
            if operation == "configure":
                return self.configure(body["runtimes"], epoch)
            if operation == "list":
                return [state["pod"] for state in self.states()]
            uid = str(uuid.UUID(body["uid"]))
            directory = self.root / "pods" / uid
            path = directory / "state.json"
            if operation == "create":
                image = body["pod"]["spec"]["containers"][0]["image"]
                digest = image.rsplit("@sha256:", 1)[-1]
                if digest not in self.config.get("runtimes", {}):
                    wanted = self.catalogue_wanted
                    if digest in wanted and image == wanted[digest]["image"]:
                        raise RuntimeStaging("Pinned bundle is still being staged")
                if self.validate(body["pod"]) != uid:
                    raise ValueError("Pod UID does not match the request")
                if not path.exists():
                    devices, port = self.assignment(body["pod"])
                    _, profile = runtime_profile(self.config, body["pod"])
                    directory.mkdir(mode=0o755, exist_ok=True)
                    directory.chmod(0o755)
                    sync_directory(directory.parent)
                    group = pod_cgroup(uid)
                    group.mkdir(exist_ok=True)
                    (group / "cpu.max").write_text(f"{int(profile['cpu']) * 100000} 100000")
                    (group / "memory.max").write_text(str(int(profile["memory"].removesuffix("Gi")) * 1024 ** 3))
                    (group / "memory.swap.max").write_text("0")
                    (group / "pids.max").write_text("8192")
                    lora = directory / "lora"
                    lora.mkdir(exist_ok=True)
                    account = pwd.getpwnam("runtime")
                    os.chown(lora, account.pw_uid, account.pw_gid)
                    if profile.get("kind") == "training":
                        training = directory / "training"
                        training.mkdir(mode=0o700, exist_ok=True)
                        os.chown(training, account.pw_uid, account.pw_gid)
                    state = {"pod": body["pod"], "draining": False, "gpu_uuids": devices, "port_base": port}
                    atomic_json(path, state)
                    self.ensure_task(state)
                    self.refresh_proxy()
                elif json.loads(path.read_text())["pod"]["spec"]["containers"][0]["image"] != body["pod"]["spec"]["containers"][0]["image"]:
                    raise ValueError("A pod UID cannot change its runtime release")
                else:
                    state = json.loads(path.read_text())
                    state["pod"] = body["pod"]
                    state["qualified_once"] = state.get("qualified_once", False) or body["pod"]["metadata"].get("annotations", {}).get("gradiated.com/qualified") == "true"
                    atomic_json(path, state)
                    self.ensure_task(state)
                return {"created": True}
            if operation == "delete":
                if path.exists():
                    state = json.loads(path.read_text())
                    if not state.get("draining"):
                        supplied = body.get("pod")
                        if supplied is not None and self.validate(supplied) != uid:
                            raise ValueError("Deletion UID does not match its pod")
                        qualified = state.get("qualified_once", False) or (supplied or state["pod"])["metadata"].get("annotations", {}).get("gradiated.com/qualified") == "true"
                        state["draining"] = True
                        state["drain_started_at"] = time.time()
                        _, profile = runtime_profile(self.config, state["pod"])
                        state["drain_seconds"] = REQUEST_DRAIN_SECONDS if qualified and profile.get("kind") != "training" else 0
                        atomic_json(path, state)
                        self.refresh_proxy()
                        threading.Thread(target=self.drain, args=(uid,), daemon=True).start()
                return {"deleted": not path.exists()}
            state = json.loads(path.read_text())
            if operation == "status":
                running = alive(state.get("task"))
                _, profile = runtime_profile(self.config, state["pod"])
                training = profile.get("kind") == "training"
                ready = running and not state.get("draining") and health(
                    state.get("port_base", 38080) + (0 if training else 1),
                    "/health" if training else "/health/ready")
                runtime_path = directory / "runtime.json"
                details = json.loads(runtime_path.read_text()) if runtime_path.exists() else {}
                return {"running": running, "ready": ready,
                        "epoch": details.get("runtime", {}), "draining": state.get("draining", False)}
            raise ValueError("Unsupported host operation")

    def drain(self, uid):
        directory = self.root / "pods" / uid
        path = directory / "state.json"
        if not path.exists():
            return
        state = json.loads(path.read_text())
        # New requests are withdrawn before the existing request drain.
        if alive(state.get("task")):
            time.sleep(max(0, state["drain_started_at"] + state.get("drain_seconds", REQUEST_DRAIN_SECONDS) - time.time()))
        self.stop(directory, state)
        group = pod_cgroup(uid)
        if group.exists():
            if (group / "cgroup.procs").read_text().strip():
                (group / "cgroup.kill").write_text("1")
                deadline = time.monotonic() + 5
                while (group / "cgroup.procs").read_text().strip() and time.monotonic() < deadline:
                    time.sleep(.1)
            if (group / "cgroup.procs").read_text().strip():
                raise RuntimeError("Pod cgroup is occupied; GPU claim retained")
            group.rmdir()
        for name in ("training", "lora"):
            cache = directory / name
            if cache.exists():
                shutil.rmtree(cache)
        with self.lock:
            path.unlink(missing_ok=True)
            sync_directory(path.parent)
            self.refresh_proxy()


def serve():
    config = json.loads(CONFIG.read_text())
    prepare_cgroups()
    agent = Agent(config, config_path=CONFIG)
    ROOT.mkdir(mode=0o755, exist_ok=True)
    ROOT.chmod(0o755)
    (ROOT / "pods").mkdir(mode=0o755, exist_ok=True)
    (ROOT / "pods").chmod(0o755)
    proxy = ROOT / "proxy"
    proxy.mkdir(mode=0o755, exist_ok=True)
    proxy.chmod(0o755)
    account = pwd.getpwnam("desmond")
    os.chown(proxy, account.pw_uid, account.pw_gid)
    lock = (ROOT / "agent.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with configuration_lock(ROOT):
        agent.ensure_proxy()

    def monitor_proxy():
        while True:
            time.sleep(2)
            with agent.lock, configuration_lock(ROOT):
                try:
                    agent.ensure_proxy()
                except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                    print(f"Proxy recovery failed: {type(error).__name__}", flush=True)

    with agent.lock, configuration_lock(ROOT):
        for state in agent.states():
            directory = ROOT / 'pods' / state['pod']['metadata']['uid']
            records = [(directory / 'state.json', state, ('task',))]
            runtime_path = directory / 'runtime.json'
            if runtime_path.exists():
                records.append((runtime_path, json.loads(runtime_path.read_text()), ('runtime', 'reporter')))
            for path, record, keys in records:
                changed = False
                for key in keys:
                    handle = record.get(key)
                    if handle and alive(handle) and any(field not in handle for field in PROCESS_SCOPE):
                        handle.update(PROCESS_SCOPE)
                        changed = True
                if changed:
                    atomic_json(path, record)
    threading.Thread(target=monitor_proxy, daemon=True).start()
    def recover():
        ticks = 0
        while True:
            try:
                with agent.lock, configuration_lock(ROOT):
                    agent.reap_children()
                    for state in agent.states():
                        agent.ensure_task(state)
                if ticks % 12 == 0:
                    agent.housekeep()
            except (OSError, ValueError, RuntimeError) as error:
                print(f'Host recovery failed: {type(error).__name__}', flush=True)
            ticks += 1
            time.sleep(5)
    threading.Thread(target=recover, daemon=True).start()
    for state in agent.states():
        if state.get("draining"):
            threading.Thread(target=agent.drain, args=(state["pod"]["metadata"]["uid"],), daemon=True).start()
    token = Path(config["token_file"]).read_text().strip()

    server = ThreadingHTTPServer(("127.0.0.1", 8887), handler_for(agent, token))
    server.serve_forever()


def handler_for(agent, token):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, *_):
            pass

        def do_POST(self):
            if self.path != "/_kubelet" or not hmac.compare_digest(self.headers.get("Authorization", ""), f"Bearer {token}"):
                self.send_error(403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 128 * 1024:
                    raise ValueError("Invalid request length")
                response = agent.request(json.loads(self.rfile.read(size)))
                payload = json.dumps(response).encode()
                self.send_response(200)
            except RuntimeStaging:
                payload = b'{"error":"runtime_staging"}'
                self.send_response(503)
            except (OSError, RuntimeError) as error:
                print(f'Host operation unavailable: {type(error).__name__}', flush=True)
                payload = b'{"error":"host_unavailable"}'
                self.send_response(503)
            except (ValueError, KeyError) as error:
                detail = f": {error}" if isinstance(error, (ValueError, FileNotFoundError)) else ""
                print(f"Host operation rejected: {type(error).__name__}{detail}", flush=True)
                payload = b'{"error":"invalid_host_operation"}'
                self.send_response(422)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "proxy":
        (CGROUP / "gradiated-proxy" / "cgroup.procs").write_text(str(os.getpid()))
        os.execv("/usr/bin/setpriv", ["setpriv", "--reuid=desmond", "--regid=desmond", "--init-groups",
                 "--inh-caps=-all", "--ambient-caps=-all", "--no-new-privs", "--pdeathsig=clear",
                 "nginx", "-c", str(ROOT / "nginx.conf"), "-g", "daemon off;"])
    elif len(sys.argv) == 3 and sys.argv[1] == "task":
        stopping = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stopping.set())
        signal.signal(signal.SIGINT, lambda *_: stopping.set())
        backoff = 5
        while not stopping.is_set():
            try:
                task(str(uuid.UUID(sys.argv[2])), stopping)
            except Exception as error:
                print(f"Runtime attempt failed: {type(error).__name__}", flush=True)
            config = json.loads(CONFIG.read_text())
            state = json.loads((ROOT / "pods" / sys.argv[2] / "state.json").read_text())
            if runtime_profile(config, state["pod"])[1].get("kind") == "training":
                break
            if stopping.wait(backoff):
                break
            backoff = min(backoff * 2, 60)
    else:
        serve()
