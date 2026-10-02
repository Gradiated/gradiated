import logging
import time

from loader import CapacityError

logger = logging.getLogger(__name__)


def start_preload(loader, targets, seconds=600):
    loader.ready = True
    try:
        deadline = time.monotonic() + seconds
        loaded = 0
        for target in loader.operation("production_list", targets):
            if (
                time.monotonic() >= deadline
                or loaded >= loader.config["cpu_adapter_slots"]
            ):
                break
            try:
                loader.prepare_version(
                    target["version_name"],
                    target["workspace_id"],
                )
                loaded += 1
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
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        logger.warning("Adapter startup preload incomplete (%s)", type(error).__name__)
