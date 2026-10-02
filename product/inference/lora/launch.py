import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from grants import production_targets, resolver, validate_endpoint
from manager import Manager
from server import create_server
from startup import start_preload


def engine_settings(command, environment, model_config):
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
        "base_model_revision": parsed.revision,
        "runtime_model_name": parsed.served_model_name or parsed.model,
        "tensor_parallel_size": parsed.tensor_parallel_size,
        "max_concurrency": parsed.max_num_seqs,
        "gpu_slots": int(environment["LORA_GPU_SLOTS"]),
        "cpu_adapter_slots": int(environment["LORA_CPU_SLOTS"]),
        "max_rank": int(environment["LORA_MAX_RANK"]),
        "cpu_cache_bytes": int(environment["LORA_CPU_CACHE_BYTES"]),
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


def main():
    from huggingface_hub import hf_hub_download

    command = sys.argv[1:]
    _settings, model, revision = engine_settings(command, os.environ, {})
    model_config = json.loads(
        Path(hf_hub_download(model, "config.json", revision=revision)).read_text()
    )
    settings, _model, _revision = engine_settings(command, os.environ, model_config)
    validate_endpoint(
        os.environ["LORA_PRODUCTION_URL"], os.environ["LORA_CONTROL_TOKEN"]
    )
    ports = [
        int(os.environ[key]) for key in ("ENGINE_PORT", "RUNTIME_PORT", "WARMUP_PORT")
    ]
    if len(set(ports)) != 3 or any(not 0 < port < 65536 for port in ports):
        raise ValueError("Runtime ports must be distinct and valid")
    manager = Manager(
        settings,
        os.environ["LORA_CACHE_DIR"],
        int(os.environ["ENGINE_PORT"]),
        {
            host.strip()
            for host in os.environ["LORA_DOWNLOAD_HOSTS"].split(",")
            if host.strip()
        },
        resolve=resolver(
            os.environ["LORA_GRANTS_URL"], os.environ["LORA_CONTROL_TOKEN"]
        ),
    )
    manager.engine_ready = False
    manager.ready = False
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
    server = create_server(
        manager, int(os.environ["RUNTIME_PORT"]), os.environ["LORA_CONTROL_TOKEN"]
    )
    try:
        child = subprocess.Popen(
            command, env={**os.environ, "VLLM_ALLOW_RUNTIME_LORA_UPDATING": "True"}
        )
    except Exception:
        server.server_close()
        raise

    def shutdown(*_args):
        child.terminate()
        threading.Thread(target=server.shutdown, daemon=True).start()

    def monitor():
        while child.poll() is None:
            if manager.failed:
                child.terminate()
                break
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
                manager,
                lambda: production_targets(
                    os.environ["LORA_PRODUCTION_URL"],
                    os.environ["LORA_CONTROL_TOKEN"],
                    settings["base_model_id"],
                ),
                int(os.environ.get("LORA_PRELOAD_SECONDS", "600")),
            )
        except (OSError, ValueError, KeyError, TypeError):
            print(
                "Adapter startup preload incomplete; on-demand loading remains available",
                file=sys.stderr,
            )
        finally:
            manager.ready = manager.engine_ready

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
    return 1 if manager.failed else child.returncode


if __name__ == "__main__":
    sys.exit(main())
