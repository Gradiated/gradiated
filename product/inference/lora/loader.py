import copy
import http.client
import json
import logging
import math
import re
import shutil
import threading
import time
import urllib.error
import uuid
from pathlib import Path

import cartridge
from artifacts import cache_key, download, has_fused_experts, materialize, remaining

logger = logging.getLogger(__name__)


class CapacityError(RuntimeError):
    pass


class CartridgeNotApplied(ValueError):
    """The cartridge loaded but did not change the canary's next-token distribution."""


# A fixed open-ended prompt, so the base model's first tokens are not forced.
CANARY_MESSAGES = [{"role": "user", "content": "In one sentence, what do you help people with?"}]
CANARY_TOKENS = 8
# Total variation between the top-20 next-token distributions; unapplied cartridges give ~0.
CANARY_MIN_DIVERGENCE = 0.02
# Each canary generation is 8 tokens; the API's probe deadline counts two of these.
CANARY_TIMEOUT_SECONDS = 30


def canary_positions(content):
    """Each position's greedy token and top-token probabilities; malformed is a runtime fault."""
    try:
        positions = [
            (
                row["token"],
                {item["token"]: math.exp(item["logprob"]) for item in row["top_logprobs"]},
            )
            for row in content
        ]
        if not positions or not all(
            isinstance(token, str) and all(isinstance(t, str) for t in top)
            for token, top in positions
        ):
            raise ValueError
        return positions
    except (KeyError, IndexError, TypeError, ValueError, OverflowError):
        raise RuntimeError("Canary logprobs are malformed") from None


def canary_divergence(with_cartridge, without):
    """Largest next-token divergence while both greedy outputs agree; a differing token is 1."""
    largest = 0.0
    for (left, p), (right, q) in zip(with_cartridge, without):
        distance = sum(abs(p.get(t, 0.0) - q.get(t, 0.0)) for t in p.keys() | q.keys())
        largest = max(largest, distance / 2)
        if left != right:
            return 1.0
    return largest


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
            adapter.get("format") not in ("peft_lora", "cartridge")
            or version["base_model_id"] != self.config["base_model_id"]
            or adapter.get("validated_base_model_revision", adapter.get("base_model_revision"))
            != self.config["base_model_revision"]
            or not re.fullmatch(r"[a-f0-9]{64}", adapter["sha256"])
            or str(uuid.UUID(version["id"])) != version["id"]
            or str(uuid.UUID(workspace)) != workspace
            or not isinstance(version["name"], str)
            or not 0 < len(version["name"]) <= 300
            or type(adapter["size_bytes"]) is not int
            or not 0 < adapter["size_bytes"] < self.config["disk_cache_bytes"]
        ):
            raise ValueError("Incompatible task version")
        if adapter["format"] == "cartridge":
            cartridge.validate_metadata(adapter, self.config["model_config"])
        elif type(adapter["rank"]) is not int or not 0 < adapter["rank"] <= self.config["max_rank"]:
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

    def engine(self, method, path, body=None, timeout=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            self.engine_port,
            timeout=timeout or (60 if method == "POST" else 5),
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

    def version_key(self, name, workspace_id, deadline=None):
        if self.resolve is None:
            raise LookupError("Version unavailable")
        spec = self.resolve(name, workspace_id, deadline)
        remaining(deadline)
        if spec["workspace_id"] != workspace_id or spec["version"]["name"] != name:
            raise ValueError("Version grant identity mismatch")
        return self.register_metadata(spec)

    def resolve_version(self, name, workspace_id):
        deadline = time.monotonic() + 60
        return self.operation(
            "resolve",
            lambda: self.resolve_files(
                self.version_key(name, workspace_id, deadline), workspace_id, deadline
            ),
        )

    def prepare_version(self, name, workspace_id):
        """Prepares the version and returns its loader key."""
        deadline = time.monotonic() + 60

        def prepare():
            key = self.version_key(name, workspace_id, deadline)
            self.prepare(key, workspace_id, deadline)
            return key

        return self.operation("prepare", prepare)

    def operation(self, action, call):
        started = time.monotonic()
        outcome = "success"
        failure = {}
        try:
            return call()
        except CapacityError:
            outcome = "capacity"
            raise
        except Exception as error:
            outcome = "failed"
            failure["error_type"] = type(error).__name__
            if isinstance(error, urllib.error.HTTPError):
                failure["upstream_status"] = error.code
            raise
        finally:
            elapsed = time.monotonic() - started
            with self.lock:
                key = (action, outcome)
                self.operations[key] = self.operations.get(key, 0) + 1
                if outcome == "failed":
                    self.counters["failures"] += 1
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
                        **failure,
                    }
                ),
            )

    def local_files(self, name):
        path = self.root / name
        adapter = self.entries[name]["spec"]["version"]["adapter"]
        if adapter["format"] == "cartridge":
            return cartridge.resolved_files(path, adapter)
        return {"path": str(path), "is_3d_lora_weight": has_fused_experts(path)}

    def resolve_files(self, name, workspace_id, deadline=None):
        if deadline is None:
            deadline = time.monotonic() + 60
        remaining(deadline)
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
        if not self.admission.acquire(timeout=max(0, deadline - time.monotonic())):
            raise TimeoutError("Cold adapter admission deadline exceeded")
        started = time.monotonic()
        try:
            if not self.loading.acquire(timeout=max(0, deadline - time.monotonic())):
                raise TimeoutError("Cold adapter materialization deadline exceeded")
            try:
                return self._prepare(name, workspace_id, deadline)
            finally:
                self.loading.release()
        except CapacityError:
            raise
        except Exception as error:
            logger.warning("Adapter preparation failed (%s)", type(error).__name__)
            raise
        finally:
            with self.lock:
                self.preparation_seconds += time.monotonic() - started
                self.preparations += 1
            self.admission.release()

    def prepare(self, name, workspace_id, deadline=None):
        files = self.resolve_files(name, workspace_id, deadline)
        # SGLang reads a cartridge from its path on first use; there is nothing to register.
        if files.get("kind") == "cartridge":
            return
        runtime_name = f"{workspace_id}/{self.entries[name]['spec']['version']['name']}"
        # SGLang's resolver hook can call the loader while it loads an adapter.
        # Do not hold the materialization lock across calls back into SGLang.
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
                    "/load_lora_adapter",
                    {"lora_name": runtime_name, "lora_path": files["path"]},
                )
            except ValueError:
                models = json.loads(self.engine("GET", "/v1/models"))["data"]
                if not any(model["id"] == runtime_name for model in models):
                    raise
            with self.lock:
                entry["registered"] = True
                self.counters["registrations"] += 1

    def _prepare(self, name, workspace_id, deadline):
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
            self.fetch(spec, path, hosts, deadline)

        def reserve(required):
            if time.monotonic() >= deadline:
                raise TimeoutError("Cold adapter deadline exceeded")
            with self.lock:
                self.reserve_disk(name, required)

        try:
            if entry["spec"]["version"]["adapter"]["format"] == "cartridge":
                _path, disk = cartridge.materialize(
                    entry["spec"],
                    self.root,
                    self.config["disk_cache_bytes"],
                    self.allowed_hosts,
                    self.config["model_config"],
                    fetch=fetch,
                    reserve=reserve,
                    deadline=deadline,
                )
            else:
                _path, disk, _tensor_bytes = materialize(
                    entry["spec"],
                    self.root,
                    self.config["disk_cache_bytes"],
                    self.allowed_hosts,
                    self.config["model_config"],
                    fetch=fetch,
                    reserve=reserve,
                    deadline=deadline,
                    allowed_target_modules=self.config.get("allowed_target_modules"),
                )
        finally:
            with self.lock:
                directory = self.root / name
                entry["disk"] = (
                    sum(item.stat().st_size for item in directory.iterdir())
                    if directory.is_dir()
                    else 0
                )
        if time.monotonic() >= deadline:
            raise TimeoutError("Cold adapter deadline exceeded")
        with self.lock:
            self.counters["disk_hits"] += int(not fetched)
            # SGLang reloads evicted adapters from the returned path.
            entry.update(disk=disk, pinned=True, used=time.time())
        return self.local_files(name)

    def probe(self, name, workspace_id):
        key = self.prepare_version(name, workspace_id)
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
        with self.lock:
            adapter = self.entries[key]["spec"]["version"]["adapter"]
        if adapter["format"] == "cartridge":
            self.cartridge_canary(f"{workspace_id}/{name}")

    def cartridge_canary(self, model):
        """Fails when the cartridge does not change the canary prompt's next-token logits."""
        served = [
            row["id"]
            for row in json.loads(self.engine("GET", "/v1/models"))["data"]
            if not row.get("parent")
        ]
        if len(served) != 1:
            raise RuntimeError("Runtime base model is ambiguous")

        def positions(name):
            result = json.loads(
                self.engine(
                    "POST",
                    "/v1/chat/completions",
                    {
                        "model": name,
                        "messages": CANARY_MESSAGES,
                        "max_tokens": CANARY_TOKENS,
                        "temperature": 0,
                        "logprobs": True,
                        "top_logprobs": 20,
                    },
                    timeout=CANARY_TIMEOUT_SECONDS,
                )
            )
            try:
                content = result["choices"][0]["logprobs"]["content"]
                if result.get("model") != name:
                    raise ValueError
            except (KeyError, IndexError, TypeError, ValueError):
                raise RuntimeError("Canary identity or logprobs mismatch") from None
            return canary_positions(content)

        if canary_divergence(positions(model), positions(served[0])) <= CANARY_MIN_DIVERGENCE:
            raise CartridgeNotApplied("Cartridge did not change the canary")

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
