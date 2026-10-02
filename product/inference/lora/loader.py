import copy
import http.client
import json
import logging
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from artifacts import cache_key, download, has_fused_experts, materialize

logger = logging.getLogger(__name__)


class CapacityError(RuntimeError):
    pass


class Loader:
    def __init__(
        self, config, root, engine_port, allowed_hosts, fetch=None, resolve=None
    ):
        self.config = config
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.engine_port = engine_port
        self.allowed_hosts = allowed_hosts
        self.fetch = fetch or download
        self.resolve = resolve
        self.boot_id = str(uuid.uuid4())
        self.lock = threading.Lock()
        self.loading = threading.Lock()
        self.registration = threading.Lock()
        self.admission = threading.BoundedSemaphore(2)
        self.entries = {}
        self.ready = False
        self.counters = dict.fromkeys(
            ("disk_hits", "downloads", "registrations", "failures", "disk_evictions"), 0
        )
        self.preparation_seconds = 0.0
        self.preparations = 0
        self.operations = {}
        self.last_failure = 0
        self.last_capacity_rejection = 0
        for path in self.root.iterdir():
            if path.is_symlink() or not path.is_dir():
                continue
            if re.fullmatch(r"[a-f0-9-]{36}-[a-f0-9]{64}\.partial", path.name):
                shutil.rmtree(path)
            elif re.fullmatch(r"[a-f0-9-]{36}-[a-f0-9]{64}", path.name):
                self.entries[path.name] = self.entry(
                    disk=sum(
                        item.stat().st_size for item in path.iterdir() if item.is_file()
                    ),
                    used=path.stat().st_mtime,
                )
        self.reserve_disk(None, 0)

    @staticmethod
    def entry(spec=None, disk=0, used=None):
        return {
            "spec": spec,
            "disk": disk,
            "used": time.time() if used is None else used,
            "pinned": False,
            "registered": False,
            "registration_attempted": False,
        }

    def disk_bytes(self):
        return sum(entry["disk"] for entry in self.entries.values())

    def reserve_disk(self, name, required):
        current = self.entries.get(name, {}).get("disk", 0)
        for key in sorted(self.entries, key=lambda key: self.entries[key]["used"]):
            if (
                self.disk_bytes() - current + required
                <= self.config["disk_cache_bytes"]
            ):
                break
            entry = self.entries[key]
            if key != name and entry["disk"] and not entry["pinned"]:
                try:
                    shutil.rmtree(self.root / key)
                except FileNotFoundError:
                    pass
                entry["disk"] = 0
                self.counters["disk_evictions"] += 1
        if self.disk_bytes() - current + required > self.config["disk_cache_bytes"]:
            raise CapacityError("Registered adapter files fill the disk budget")

    def register_metadata(self, spec):
        spec = copy.deepcopy(spec)
        version, workspace = spec["version"], spec["workspace_id"]
        adapter = version["adapter"]
        if (
            adapter.get("format") != "peft_lora"
            or version["base_model_id"] != self.config["base_model_id"]
            or adapter.get("base_model_revision") != self.config["base_model_revision"]
            or not re.fullmatch(r"[a-f0-9]{64}", adapter["sha256"])
            or str(uuid.UUID(version["id"])) != version["id"]
            or str(uuid.UUID(workspace)) != workspace
            or not isinstance(version["name"], str)
            or not 0 < len(version["name"]) <= 300
            or type(adapter["rank"]) is not int
            or not 0 < adapter["rank"] <= self.config["max_rank"]
            or type(adapter["size_bytes"]) is not int
            or not 0 < adapter["size_bytes"] < self.config["disk_cache_bytes"]
        ):
            raise ValueError("Incompatible task version")
        spec["version"] = {
            "id": version["id"],
            "name": version["name"],
            "base_model_id": version["base_model_id"],
            "adapter": adapter,
        }
        name = cache_key(version)
        with self.lock:
            entry = self.entries.get(name)
            if (
                entry
                and entry["spec"]
                and any(
                    entry["spec"][key] != spec[key]
                    for key in ("workspace_id", "version")
                )
            ):
                raise ValueError("Immutable adapter replacement")
            if entry is None:
                if len(self.entries) >= 4096:
                    idle = [
                        key
                        for key, value in self.entries.items()
                        if not value["disk"] and not value["pinned"]
                    ]
                    if not idle:
                        raise CapacityError("Adapter metadata registry full")
                    del self.entries[
                        min(idle, key=lambda key: self.entries[key]["used"])
                    ]
                entry = self.entries[name] = self.entry()
            entry["spec"] = spec
        return name

    def engine(self, method, path, body=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.engine_port, timeout=60 if method == "POST" else 5
        )
        try:
            connection.request(
                method,
                path,
                json.dumps(body) if body is not None else None,
                {"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            data = response.read(1024 * 1024 + 1)
            if 400 <= response.status < 500:
                raise ValueError("Runtime rejected adapter operation")
            if response.status != 200 or len(data) > 1024 * 1024:
                raise RuntimeError("Runtime adapter operation failed")
            return data
        finally:
            connection.close()

    def version_key(self, name, workspace_id):
        if self.resolve is None:
            raise LookupError("Version unavailable")
        spec = self.resolve(name, workspace_id)
        if spec["workspace_id"] != workspace_id or spec["version"]["name"] != name:
            raise ValueError("Version grant identity mismatch")
        return self.register_metadata(spec)

    def resolve_version(self, name, workspace_id):
        return self.operation(
            "resolve",
            lambda: self.resolve_files(
                self.version_key(name, workspace_id), workspace_id
            ),
        )

    def prepare_version(self, name, workspace_id):
        return self.operation(
            "prepare",
            lambda: self.prepare(self.version_key(name, workspace_id), workspace_id),
        )

    def operation(self, action, call):
        started = time.monotonic()
        outcome = "success"
        try:
            return call()
        except CapacityError:
            outcome = "capacity"
            raise
        except Exception:
            outcome = "failed"
            raise
        finally:
            elapsed = time.monotonic() - started
            with self.lock:
                key = (action, outcome)
                self.operations[key] = self.operations.get(key, 0) + 1
                if outcome == "failed":
                    self.last_failure = time.time()
                if outcome == "capacity":
                    self.last_capacity_rejection = time.time()
            logger.log(
                logging.INFO if outcome == "success" else logging.WARNING,
                json.dumps(
                    {
                        "event": "lora_operation",
                        "action": action,
                        "outcome": outcome,
                        "elapsed_seconds": round(elapsed, 3),
                    }
                ),
            )

    def local_files(self, name):
        path = self.root / name
        return {"path": str(path), "is_3d_lora_weight": has_fused_experts(path)}

    def resolve_files(self, name, workspace_id):
        if not self.ready:
            raise CapacityError("Base engine warming")
        with self.lock:
            entry = self.entries.get(name)
            if entry and entry["spec"]:
                if entry["spec"]["workspace_id"] != workspace_id:
                    raise LookupError("Adapter unavailable")
                if entry["pinned"]:
                    entry["used"] = time.time()
                    return self.local_files(name)
        if not self.admission.acquire(blocking=False):
            raise CapacityError("Preparation at capacity")
        started = time.monotonic()
        try:
            if not self.loading.acquire(timeout=60):
                raise CapacityError("Preparation busy")
            try:
                return self._prepare(name, workspace_id)
            finally:
                self.loading.release()
        except CapacityError:
            raise
        except Exception as error:
            with self.lock:
                self.counters["failures"] += 1
            logger.warning("Adapter preparation failed (%s)", type(error).__name__)
            raise
        finally:
            with self.lock:
                self.preparation_seconds += time.monotonic() - started
                self.preparations += 1
            self.admission.release()

    def prepare(self, name, workspace_id):
        files = self.resolve_files(name, workspace_id)
        runtime_name = f"{workspace_id}/{self.entries[name]['spec']['version']['name']}"
        # Native resolution can call the loader while holding vLLM's model lock.
        # Do not hold the materialization lock across calls back into vLLM.
        with self.registration:
            entry = self.entries[name]
            if entry["registered"]:
                return
            if entry["registration_attempted"]:
                models = json.loads(self.engine("GET", "/v1/models"))["data"]
                if any(model["id"] == runtime_name for model in models):
                    with self.lock:
                        entry["registered"] = True
                    return
            entry["registration_attempted"] = True
            try:
                self.engine(
                    "POST",
                    "/v1/load_lora_adapter",
                    {
                        "lora_name": runtime_name,
                        "lora_path": files["path"],
                        "is_3d_lora_weight": files["is_3d_lora_weight"],
                    },
                )
            except ValueError:
                models = json.loads(self.engine("GET", "/v1/models"))["data"]
                if not any(model["id"] == runtime_name for model in models):
                    raise
            with self.lock:
                entry["registered"] = True
                self.counters["registrations"] += 1

    def _prepare(self, name, workspace_id):
        with self.lock:
            entry = self.entries.get(name)
            if (
                entry
                and entry["spec"]
                and entry["spec"]["workspace_id"] != workspace_id
            ):
                raise LookupError("Adapter unavailable")
            if entry and entry["pinned"]:
                return self.local_files(name)
        if name not in self.entries or not self.entries[name]["spec"]:
            raise LookupError("Adapter unavailable")
        entry = self.entries[name]
        fetched = False

        def fetch(spec, path, hosts):
            nonlocal fetched
            fetched = True
            with self.lock:
                self.counters["downloads"] += 1
            self.fetch(spec, path, hosts)

        def reserve(required):
            with self.lock:
                self.reserve_disk(name, required)

        try:
            _path, disk, _tensor_bytes = materialize(
                entry["spec"],
                self.root,
                self.config["disk_cache_bytes"],
                self.allowed_hosts,
                self.config["model_config"],
                fetch=fetch,
                reserve=reserve,
            )
        finally:
            with self.lock:
                directory = self.root / name
                entry["disk"] = (
                    sum(item.stat().st_size for item in directory.iterdir())
                    if directory.is_dir()
                    else 0
                )
        with self.lock:
            self.counters["disk_hits"] += int(not fetched)
            # vLLM retains returned paths for native CPU-cache reloads.
            entry.update(disk=disk, pinned=True, used=time.time())
        return self.local_files(name)

    def probe(self, name, workspace_id):
        self.prepare_version(name, workspace_id)
        result = json.loads(
            self.engine(
                "POST",
                "/v1/chat/completions",
                {
                    "model": f"{workspace_id}/{name}",
                    "messages": [{"role": "user", "content": "Reply with READY."}],
                    "max_tokens": 8,
                    "temperature": 0,
                },
            )
        )
        if (
            result.get("model") != f"{workspace_id}/{name}"
            or not result.get("choices")
            or not result.get("usage", {}).get("completion_tokens", 0)
        ):
            raise RuntimeError("Adapter probe identity or usage mismatch")

    def status(self):
        with self.lock:
            return {
                "boot_id": self.boot_id,
                "ready": self.ready,
                "disk_cache_bytes": self.disk_bytes(),
                "registered_adapters": sum(
                    entry["registered"] for entry in self.entries.values()
                ),
            }

    def metrics(self):
        with self.lock:
            values = {
                **{f"{key}_total": value for key, value in self.counters.items()},
                "preparation_seconds_sum": self.preparation_seconds,
                "preparation_seconds_count": self.preparations,
                "disk_cache_bytes": self.disk_bytes(),
                "disk_cache_limit_bytes": self.config["disk_cache_bytes"],
                "pinned_disk_bytes": sum(
                    entry["disk"] for entry in self.entries.values() if entry["pinned"]
                ),
                "last_failure_timestamp_seconds": self.last_failure,
                "last_capacity_rejection_timestamp_seconds": self.last_capacity_rejection,
            }
            gauges = "".join(
                f"gradiated_lora_{key} {value}\n" for key, value in values.items()
            )
            operations = "".join(
                f'gradiated_lora_operations_total{{action="{action}",outcome="{outcome}"}} {count}\n'
                for (action, outcome), count in sorted(self.operations.items())
            )
            return (gauges + operations).encode()
