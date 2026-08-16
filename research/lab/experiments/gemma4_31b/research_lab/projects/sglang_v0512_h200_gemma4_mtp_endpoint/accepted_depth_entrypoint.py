#!/usr/bin/env python3
from __future__ import annotations

import proven_v0513_endpoint_entrypoint as endpoint


def audited_run_scheduler_process(*args, **kwargs):
    endpoint.install_audit()
    from accepted_depth_discriminator import install

    install()
    from sglang.srt.managers.scheduler import run_scheduler_process

    return run_scheduler_process(*args, **kwargs)


endpoint.audited_run_scheduler_process = audited_run_scheduler_process


if __name__ == "__main__":
    endpoint.main()
