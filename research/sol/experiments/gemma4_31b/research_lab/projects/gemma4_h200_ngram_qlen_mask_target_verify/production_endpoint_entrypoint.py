from __future__ import annotations

import os

from endpoint_entrypoint import install_audit, main


if os.environ.get("QLEN_CAPTURE_ARTIFACT"):
    import endpoint_entrypoint

    def audited_run_scheduler_process(*args, **kwargs):
        install_audit()
        from production_capture_hook import install

        install()
        from sglang.srt.managers.scheduler import run_scheduler_process

        return run_scheduler_process(*args, **kwargs)

    endpoint_entrypoint.audited_run_scheduler_process = audited_run_scheduler_process


if __name__ == "__main__":
    main()

