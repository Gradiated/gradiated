import time

from manager import CapacityError


def preload_production(manager, targets, seconds=600):
    deadline = time.monotonic() + seconds
    for target in targets:
        if time.monotonic() >= deadline or manager.failed:
            break
        with manager.lock:
            if (
                sum(entry["cpu_resident"] for entry in manager.entries.values())
                >= manager.config["cpu_adapter_slots"]
            ):
                break
        name = f"ft-{target['version_id']}-{target['sha256']}"
        try:
            manager.prepare(name, target["workspace_id"], preload=True)
        except (CapacityError, LookupError, ValueError, OSError, RuntimeError):
            continue
