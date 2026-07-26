import os
import pathlib
import time


try:
    from diverse_hidden_capture_hook import install_from_environment

    install_from_environment()
except Exception as exc:
    audit = os.environ.get("DIVERSE_HIDDEN_CAPTURE_AUDIT")
    if audit:
        from diverse_hidden_capture_hook import _append_audit

        _append_audit(
            pathlib.Path(audit),
            {
                "event": "capture_hook_install_error",
                "error": repr(exc),
                "time_unix_s": time.time(),
            },
        )
