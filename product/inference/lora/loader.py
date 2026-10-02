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

from artifacts import download, has_fused_experts, materialize

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
        self.admission = threading.BoundedSemaphore(2)
        self.entries = {}
        self.ready = False
        self.counters = dict.fromkeys(
            ("disk_hits", "downloads", "registrations", "failures", "disk_evictions"), 0
        )
        self.preparation_seconds = 0.0
        self.preparations = 0
        for path in self.root.iterdir():
            if path.is_symlink() or not path.is_dir():
                continue
            if re.fullmatch(r"ft-[a-f0-9-]{36}-[a-f0-9]{64}\.partial", path.name):
                shutil.rmtree(path)
            elif re.fullmatch(r"ft-[a-f0-9-]{36}-[a-f0-9]{64}", path.name):
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
        name = f"ft-{version['id']}-{adapter['sha256']}"
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

    def prepare(self, name, workspace_id):
        if not self.ready:
            raise CapacityError("Base engine warming")
        with self.lock:
            entry = self.entries.get(name)
            if (
                entry
                and entry["spec"]
                and entry["spec"]["workspace_id"] != workspace_id
            ):
                raise LookupError("Adapter unavailable")
            if entry and entry["registered"]:
                entry["used"] = time.time()
                return
        if not self.admission.acquire(blocking=False):
            raise CapacityError("Preparation at capacity")
        started = time.monotonic()
        try:
            if not self.loading.acquire(timeout=60):
                raise CapacityError("Preparation busy")
            try:
                self._prepare(name, workspace_id)
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

    def _prepare(self, name, workspace_id):
        with self.lock:
            entry = self.entries.get(name)
            if (
                entry
                and entry["spec"]
                and entry["spec"]["workspace_id"] != workspace_id
            ):
                raise LookupError("Adapter unavailable")
            if entry and entry["registered"]:
                return
            needs_grant = not entry or not entry["spec"] or not entry["disk"]
        if (
            needs_grant
            and self.resolve
            and self.register_metadata(self.resolve(name, workspace_id)) != name
        ):
            raise ValueError("Adapter identity mismatch")
        if name not in self.entries or not self.entries[name]["spec"]:
            raise LookupError("Adapter unavailable")
        entry = self.entries[name]
        if entry["pinned"]:
            models = json.loads(self.engine("GET", "/v1/models"))["data"]
            if any(model["id"] == name for model in models):
                with self.lock:
                    entry["registered"] = True
                return
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
            path, disk, _tensor_bytes = materialize(
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
            # A timed-out registration may finish later and need this reload path.
            entry.update(disk=disk, pinned=True, used=time.time())
        try:
            self.engine(
                "POST",
                "/v1/load_lora_adapter",
                {
                    "lora_name": name,
                    "lora_path": str(path),
                    "is_3d_lora_weight": has_fused_experts(path),
                },
            )
        except ValueError:
            models = json.loads(self.engine("GET", "/v1/models"))["data"]
            if any(model["id"] == name for model in models):
                with self.lock:
                    entry["registered"] = True
                return
            with self.lock:
                entry["pinned"] = False
            raise
        with self.lock:
            entry["registered"] = True
            self.counters["registrations"] += 1

    def probe(self, name, workspace_id):
        self.prepare(name, workspace_id)
        result = json.loads(
            self.engine(
                "POST",
                "/v1/chat/completions",
                {
                    "model": name,
                    "messages": [{"role": "user", "content": "Reply with READY."}],
                    "max_tokens": 8,
                    "temperature": 0,
                },
            )
        )
        if (
            result.get("model") != name
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
            }
            return "".join(
                f"gradiated_lora_{key} {value}\n" for key, value in values.items()
            ).encode()
