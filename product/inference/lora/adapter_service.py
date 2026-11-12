import json
import logging
import sys
import threading
import urllib.request
from pathlib import Path

from grants import production_targets, resolver, validate_endpoint
from loader import Loader
from server import create_server
from startup import start_preload


def download_hosts(environment):
    hosts = {
        host.strip()
        for host in environment.get("LORA_DOWNLOAD_HOSTS", "").split(",")
        if host.strip()
    }
    if not hosts:
        raise ValueError("LORA_DOWNLOAD_HOSTS must allow at least one download host")
    return hosts


def engine_settings(environment, revision, tensor_parallel_size, model_config):
    """Loader settings for one SGLang allocation; the runtime owns model and TP."""
    download_hosts(environment)
    settings = {
        "base_model_id": environment["MODEL_ID"],
        "base_model_revision": environment.get("LORA_BASE_MODEL_REVISION") or revision,
        "tensor_parallel_size": tensor_parallel_size,
        "gpu_slots": int(environment["LORA_GPU_SLOTS"]),
        "cpu_adapter_slots": int(environment["LORA_CPU_SLOTS"]),
        "max_rank": int(environment["LORA_MAX_RANK"]),
        "disk_cache_bytes": int(environment["LORA_DISK_CACHE_BYTES"]),
        "model_config": model_config,
    }
    for key, value in settings.items():
        if isinstance(value, int) and value <= 0:
            raise ValueError(f"Invalid runtime setting: {key}")
    if settings["gpu_slots"] > settings["cpu_adapter_slots"]:
        raise ValueError("GPU slots exceed CPU adapter slots")
    if (
        len(environment["NVIDIA_VISIBLE_DEVICES"].split(","))
        != settings["tensor_parallel_size"]
    ):
        raise ValueError("Runtime GPU assignment mismatch")
    return settings


def engine_arguments(settings, target_modules):
    """Native SGLang multi-LoRA flags: GPU slots per batch and CPU-resident adapters."""
    return [
        "--enable-lora",
        "--max-lora-rank",
        str(settings["max_rank"]),
        "--max-loras-per-batch",
        str(settings["gpu_slots"]),
        "--max-loaded-loras",
        str(settings["cpu_adapter_slots"]),
        "--lora-target-modules",
        *target_modules,
    ]


def resolver_environment(environment):
    """Let SGLang resolve unknown adapter names through the allocation's loader."""
    return {
        **environment,
        "SGLANG_LORA_RESOLVER_URL": f"http://127.0.0.1:{int(environment['ADAPTER_PORT'])}/internal/adapters/resolve",
    }


def ports(environment, engine_port):
    values = [
        int(environment[key]) for key in ("ADAPTER_PORT", "RUNTIME_PORT", "WARMUP_PORT")
    ] + [int(engine_port)]
    if len(set(values)) != 4 or any(not 0 < port < 65536 for port in values):
        raise ValueError("Runtime ports must be distinct and valid")


class AdapterService:
    """Loopback adapter control service that runs beside one SGLang engine.

    It is not an inference proxy: SGLang owns batching, CPU/GPU adapter slots
    and eviction. The service materializes verified adapter files for SGLang's
    resolver hook and preloads production versions once warmup qualifies.
    """

    def __init__(self, environment, settings, engine_port):
        api_base_url = environment["GRADIATED_API_BASE_URL"]
        validate_endpoint(api_base_url)
        ports(environment, engine_port)
        self.environment = environment
        self.api_base_url = api_base_url
        self.settings = settings
        self.loader = Loader(
            settings,
            environment.get("LORA_CACHE_DIR")
            or str(Path(environment["GRADIATED_RUNTIME_DIR"]) / "lora"),
            int(engine_port),
            download_hosts(environment),
            resolve=resolver(api_base_url),
        )
        self.loader.ready = False
        self.server = create_server(self.loader, int(environment["ADAPTER_PORT"]))
        self.stopping = threading.Event()

    def start(self, engine_alive):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=self.warm, args=(engine_alive,), daemon=True).start()

    def warm(self, engine_alive):
        try:
            while engine_alive() and not self.stopping.is_set():
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.environment['WARMUP_PORT']}/health",
                        timeout=5,
                    ) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
                self.stopping.wait(1)
            if not engine_alive() or self.stopping.is_set():
                return
            start_preload(
                self.loader,
                lambda: production_targets(
                    self.api_base_url, self.settings["base_model_id"]
                ),
                int(self.environment.get("LORA_PRELOAD_SECONDS", "600")),
            )
        except (OSError, ValueError, KeyError, TypeError):
            print(
                "Adapter startup preload incomplete; on-demand loading remains available",
                file=sys.stderr,
            )

    def stop(self):
        self.stopping.set()
        self.server.shutdown()
        self.server.server_close()


def model_config(model, revision):
    from huggingface_hub import hf_hub_download

    return json.loads(
        Path(hf_hub_download(model, "config.json", revision=revision)).read_text()
    )


def start(environment, model, revision, tensor_parallel_size, engine_port, alive):
    """Start the adapter service; returns it and the engine environment."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = engine_settings(
        environment, revision, tensor_parallel_size, model_config(model, revision)
    )
    service = AdapterService(environment, settings, engine_port)
    service.start(alive)
    return service, resolver_environment(environment)
