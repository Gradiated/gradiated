import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
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


def engine_settings(command, environment, model_config):
    download_hosts(environment)
    arguments = command[command.index("serve") + 1 :]
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("model")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--served-model-name")
    parser.add_argument("--tensor-parallel-size", type=int, default=1)
    parser.add_argument("--max-num-seqs", type=int, default=16)
    parsed, _unknown = parser.parse_known_args(arguments)
    settings = {
        "base_model_id": environment["MODEL_ID"],
        "base_model_revision": environment.get("LORA_BASE_MODEL_REVISION")
        or parsed.revision,
        "runtime_model_name": parsed.served_model_name or parsed.model,
        "tensor_parallel_size": parsed.tensor_parallel_size,
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
        != parsed.tensor_parallel_size
    ):
        raise ValueError("Runtime GPU assignment mismatch")
    return settings, parsed.model, parsed.revision


def resolver_environment(environment):
    plugins = [item for item in environment.get("VLLM_PLUGINS", "").split(",") if item]
    plugins.append("gradiated_lora")
    return {
        **environment,
        "VLLM_ALLOW_RUNTIME_LORA_UPDATING": "True",
        "VLLM_PLUGINS": ",".join(dict.fromkeys(plugins)),
    }


def main():
    from huggingface_hub import hf_hub_download

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    command = sys.argv[1:]
    _settings, model, revision = engine_settings(command, os.environ, {})
    api_base_url = os.environ["GRADIATED_API_BASE_URL"]
    model_config = json.loads(
        Path(hf_hub_download(model, "config.json", revision=revision)).read_text()
    )
    settings, _model, _revision = engine_settings(command, os.environ, model_config)
    validate_endpoint(api_base_url)
    ports = [
        int(os.environ[key]) for key in ("ADAPTER_PORT", "RUNTIME_PORT", "WARMUP_PORT")
    ]
    if len(set(ports)) != 3 or any(not 0 < port < 65536 for port in ports):
        raise ValueError("Runtime ports must be distinct and valid")
    loader = Loader(
        settings,
        os.environ["LORA_CACHE_DIR"],
        int(os.environ["RUNTIME_PORT"]),
        download_hosts(os.environ),
        resolve=resolver(api_base_url),
    )
    loader.ready = False
    command += [
        "--enable-lora",
        "--max-loras",
        str(settings["gpu_slots"]),
        "--max-cpu-loras",
        str(settings["cpu_adapter_slots"]),
        "--max-lora-rank",
        str(settings["max_rank"]),
        "--enable-mixed-moe-lora-format",
    ]
    server = create_server(loader, int(os.environ["ADAPTER_PORT"]))
    try:
        child = subprocess.Popen(command, env=resolver_environment(os.environ))
    except Exception:
        server.server_close()
        raise

    def shutdown(*_args):
        child.terminate()
        threading.Thread(target=server.shutdown, daemon=True).start()

    def monitor():
        while child.poll() is None:
            time.sleep(0.5)
        server.shutdown()

    def warm():
        try:
            while child.poll() is None:
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{os.environ['WARMUP_PORT']}/health",
                        timeout=5,
                    ) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
                time.sleep(1)
            if child.poll() is not None:
                return
            start_preload(
                loader,
                lambda: production_targets(
                    api_base_url,
                    settings["base_model_id"],
                ),
                int(os.environ.get("LORA_PRELOAD_SECONDS", "600")),
            )
        except (OSError, ValueError, KeyError, TypeError):
            print(
                "Adapter startup preload incomplete; on-demand loading remains available",
                file=sys.stderr,
            )

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    threading.Thread(target=monitor, daemon=True).start()
    threading.Thread(target=warm, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        child.terminate()
        try:
            child.wait(timeout=30)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
    return child.returncode


if __name__ == "__main__":
    sys.exit(main())
