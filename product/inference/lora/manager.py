import contextlib
import copy
import http.client
import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from artifacts import has_fused_experts, materialize


class CapacityError(RuntimeError):
    pass


class Manager:
    def __init__(
        self, config, root, engine_port, allowed_hosts, fetch=None, resolve=None
    ):
        self.config = config
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.engine_port = engine_port
        self.allowed_hosts = allowed_hosts
        self.fetch = fetch
        self.resolve = resolve
        self.boot_id = str(uuid.uuid4())
        self.lock = threading.Lock()
        self.loading = threading.Lock()
        self.capacity = threading.BoundedSemaphore(config["max_concurrency"])
        self.entries = {}
        self.failed = False
        self.engine_ready = True
        self.ready = True
        for path in self.root.iterdir():
            if (
                re.fullmatch(r"ft-[a-f0-9-]{36}-[a-f0-9]{64}\.partial", path.name)
                and path.is_dir()
                and not path.is_symlink()
            ):
                shutil.rmtree(path)
            elif (
                re.fullmatch(r"ft-[a-f0-9-]{36}-[a-f0-9]{64}", path.name)
                and path.is_dir()
                and not path.is_symlink()
            ):
                size = sum(
                    item.stat().st_size for item in path.iterdir() if item.is_file()
                )
                self.entries[path.name] = {
                    "spec": None,
                    "cpu_resident": False,
                    "active": 0,
                    "disk": size,
                    "cpu": 0,
                    "tensor_bytes": 0,
                    "used": time.monotonic()
                    - max(0, time.time() - path.stat().st_mtime),
                }
        for name in sorted(self.entries, key=lambda key: self.entries[key]["used"]):
            if self.used_bytes("disk") <= self.config["disk_cache_bytes"]:
                break
            self.evict(name, disk=True)
            del self.entries[name]

    def engine(self, path, body):
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            self.engine_port,
            timeout=10 if path == "/v1/unload_lora_adapter" else 60,
        )
        try:
            connection.request(
                "POST", path, json.dumps(body), {"Content-Type": "application/json"}
            )
            response = connection.getresponse()
            data = response.read(65537)
            if 400 <= response.status < 500:
                raise ValueError("Runtime rejected adapter")
            if response.status != 200 or len(data) > 65536:
                raise RuntimeError("Runtime adapter operation failed")
        finally:
            connection.close()

    def register(self, spec):
        spec = copy.deepcopy(spec)
        version = spec["version"]
        adapter = version["adapter"]
        name = f"ft-{version['id']}-{adapter['sha256']}"
        if (
            adapter.get("format") != "peft_lora"
            or version["base_model_id"] != self.config["base_model_id"]
            or adapter.get("base_model_revision") != self.config["base_model_revision"]
            or not re.fullmatch(r"[a-f0-9]{64}", adapter["sha256"])
            or str(uuid.UUID(version["id"])) != version["id"]
            or str(uuid.UUID(spec["workspace_id"])) != spec["workspace_id"]
            or type(adapter["rank"]) is not int
            or not 0 < adapter["rank"] <= self.config["max_rank"]
            or type(adapter["size_bytes"]) is not int
            or not 0 < adapter["size_bytes"] < self.config["disk_cache_bytes"]
        ):
            raise ValueError("Incompatible task version")
        spec["version"] = {
            "id": version["id"],
            "base_model_id": version["base_model_id"],
            "adapter": adapter,
        }
        with self.lock:
            previous = self.entries.get(name)
            if previous and previous["spec"]:
                old = {
                    key: value
                    for key, value in previous["spec"].items()
                    if key != "download"
                }
                new = {key: value for key, value in spec.items() if key != "download"}
                if old != new:
                    raise ValueError("Immutable adapter replacement")
                previous["spec"] = spec
            elif previous:
                previous["spec"] = spec
            else:
                if len(self.entries) >= max(4096, self.config["cpu_adapter_slots"]):
                    candidates = [
                        key
                        for key, entry in self.entries.items()
                        if not entry["disk"]
                        and not entry["cpu_resident"]
                        and not entry["active"]
                    ]
                    if not candidates:
                        raise CapacityError("Adapter registry full")
                    del self.entries[
                        min(candidates, key=lambda key: self.entries[key]["used"])
                    ]
                self.entries[name] = {
                    "spec": spec,
                    "cpu_resident": False,
                    "active": 0,
                    "disk": 0,
                    "cpu": 0,
                    "tensor_bytes": 0,
                    "used": time.monotonic(),
                }

    def used_bytes(self, tier):
        return sum(entry[tier] for entry in self.entries.values())

    def evict(self, name, disk=False):
        entry = self.entries[name]
        if entry["active"]:
            raise CapacityError("Adapter in use")
        if entry["cpu_resident"] and not disk:
            try:
                self.engine("/v1/unload_lora_adapter", {"lora_name": name})
            except Exception:
                self.failed = True
                raise
            entry["cpu_resident"] = False
            entry["cpu"] = 0
        if disk:
            try:
                shutil.rmtree(self.root / name)
            except FileNotFoundError:
                pass
            entry["disk"] = 0

    def probe(self, name):
        with self.request(name):
            connection = http.client.HTTPConnection(
                "127.0.0.1", self.engine_port, timeout=60
            )
            try:
                connection.request(
                    "POST",
                    "/v1/chat/completions",
                    json.dumps(
                        {
                            "model": name,
                            "messages": [
                                {"role": "user", "content": "Reply with READY."}
                            ],
                            "max_tokens": 8,
                            "temperature": 0,
                        }
                    ),
                    {"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                data = response.read(65537)
                if response.status != 200 or len(data) > 65536:
                    raise RuntimeError("Adapter probe failed")
                result = json.loads(data)
                if (
                    result.get("model") != name
                    or not result.get("choices")
                    or not result.get("usage", {}).get("completion_tokens", 0)
                ):
                    raise RuntimeError("Adapter probe identity or usage mismatch")
            finally:
                connection.close()

    def prepare(self, name, workspace_id=None, preload=False):
        if not self.engine_ready:
            raise CapacityError("Base engine warming")
        with self.lock:
            entry = self.entries.get(name)
            if self.failed or (not entry and not self.resolve):
                raise LookupError("Adapter unavailable")
            if (
                entry
                and entry["spec"]
                and workspace_id
                and entry["spec"]["workspace_id"] != workspace_id
            ):
                raise LookupError("Adapter unavailable")
            if entry and entry["cpu_resident"]:
                entry["used"] = time.monotonic()
                return
        if not self.loading.acquire(timeout=60):
            raise CapacityError("Preparation busy")
        try:
            with self.lock:
                entry = self.entries.get(name)
                needs_grant = not entry or not entry["spec"] or not entry["disk"]
            if needs_grant and self.resolve:
                if not workspace_id:
                    raise LookupError("Missing workspace")
                self.register(self.resolve(name, workspace_id))
            with self.lock:
                entry = self.entries.get(name)
                if self.failed or not entry or not entry["spec"]:
                    raise LookupError("Adapter unavailable")
                if workspace_id and entry["spec"]["workspace_id"] != workspace_id:
                    raise LookupError("Adapter unavailable")
                if entry["cpu_resident"]:
                    return
                spec = entry["spec"]
                factor = self.config["tensor_parallel_size"] * 2
                idle = sorted(
                    (
                        (key, item)
                        for key, item in self.entries.items()
                        if key != name and not item["active"]
                    ),
                    key=lambda pair: pair[1]["used"],
                )
                for key, item in idle:
                    if (
                        sum(item["cpu_resident"] for item in self.entries.values())
                        < self.config["cpu_adapter_slots"]
                    ):
                        break
                    if item["cpu_resident"]:
                        if preload:
                            raise CapacityError("Preload CPU slots full")
                        self.evict(key)
                if (
                    sum(item["cpu_resident"] for item in self.entries.values())
                    >= self.config["cpu_adapter_slots"]
                ):
                    raise CapacityError("All adapter slots active")
                max_disk = min(
                    self.config["disk_cache_bytes"],
                    self.config["cpu_cache_bytes"] // factor
                    + spec["version"]["adapter"]["size_bytes"]
                    + 2 * 1024 * 1024
                    + 4096,
                )

            def reserve_disk(required):
                with self.lock:
                    for key, item in idle:
                        if (
                            self.used_bytes("disk") - entry["disk"] + required
                            <= self.config["disk_cache_bytes"]
                        ):
                            break
                        if not item["active"]:
                            self.evict(key, disk=True)
                    if (
                        self.used_bytes("disk") - entry["disk"] + required
                        > self.config["disk_cache_bytes"]
                    ):
                        raise CapacityError("Adapter disk budget exhausted")

            if entry["disk"] and entry["tensor_bytes"]:
                path, disk_bytes, tensor_bytes = (
                    self.root / name,
                    entry["disk"],
                    entry["tensor_bytes"],
                )
            else:
                try:
                    path, disk_bytes, tensor_bytes = materialize(
                        spec,
                        self.root,
                        max_disk,
                        self.allowed_hosts,
                        self.config["model_config"],
                        reserve=reserve_disk,
                        **({"fetch": self.fetch} if self.fetch else {}),
                    )
                except Exception:
                    with self.lock:
                        directory = self.root / name
                        size = (
                            sum(item.stat().st_size for item in directory.iterdir())
                            if directory.is_dir()
                            else 0
                        )
                        entry.update(disk=size, tensor_bytes=0)
                    raise
            with self.lock:
                entry.update(disk=disk_bytes, tensor_bytes=tensor_bytes)
                required = tensor_bytes * factor
                if required > self.config["cpu_cache_bytes"]:
                    raise CapacityError("Adapter exceeds CPU budget")
                for key, item in idle:
                    if (
                        self.used_bytes("cpu") + required
                        <= self.config["cpu_cache_bytes"]
                    ):
                        break
                    if item["cpu_resident"]:
                        if preload:
                            raise CapacityError("Preload CPU bytes full")
                        self.evict(key)
                if self.used_bytes("cpu") + required > self.config["cpu_cache_bytes"]:
                    raise CapacityError("All CPU cache capacity active")
            try:
                self.engine(
                    "/v1/load_lora_adapter",
                    {
                        "lora_name": name,
                        "lora_path": str(path),
                        "is_3d_lora_weight": has_fused_experts(path),
                    },
                )
            except ValueError:
                raise
            except Exception:
                with self.lock:
                    self.failed = True
                raise
            with self.lock:
                entry.update(
                    cpu_resident=True,
                    disk=disk_bytes,
                    cpu=tensor_bytes * factor,
                    used=time.monotonic(),
                )
        finally:
            self.loading.release()

    @contextlib.contextmanager
    def request(self, model, workspace_id=None):
        if not self.engine_ready:
            raise CapacityError("Base engine warming")
        if not self.capacity.acquire(blocking=False):
            raise CapacityError("Allocation at capacity")
        entry = None
        try:
            if model.startswith("ft-"):
                while True:
                    self.prepare(model, workspace_id)
                    with self.lock:
                        entry = self.entries.get(model)
                        if entry and entry["cpu_resident"]:
                            entry["active"] += 1
                            break
            elif model != self.config["runtime_model_name"]:
                raise LookupError("Unknown runtime model")
            if self.failed:
                raise CapacityError("Runtime state uncertain")
            yield
        finally:
            with self.lock:
                if entry:
                    entry["active"] -= 1
                    entry["used"] = time.monotonic()
            self.capacity.release()

    def remove(self, name):
        if not self.loading.acquire(timeout=1):
            raise CapacityError("Preparation busy")
        try:
            with self.lock:
                if name not in self.entries:
                    return
                self.evict(name)
                self.evict(name, disk=True)
                del self.entries[name]
        finally:
            self.loading.release()

    def status(self):
        with self.lock:
            return {
                "boot_id": self.boot_id,
                "healthy": not self.failed,
                "cpu_cache_bytes": self.used_bytes("cpu"),
                "disk_cache_bytes": self.used_bytes("disk"),
                "adapters": [
                    {
                        "name": name,
                        "cpu_resident": entry["cpu_resident"],
                        "active": entry["active"],
                    }
                    for name, entry in self.entries.items()
                ],
            }
