import logging
import time

from manager import CapacityError

logger = logging.getLogger(__name__)


def start_preload(manager, targets, seconds=600):
    manager.engine_ready = True
    manager.ready = True
    try:
        preload_production(manager, targets(), seconds)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        logger.warning("Adapter startup preload incomplete (%s)", type(error).__name__)


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
        except (
            CapacityError,
            LookupError,
            ValueError,
            KeyError,
            TypeError,
            OSError,
            RuntimeError,
        ):
            continue
