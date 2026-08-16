from __future__ import annotations

import json
import os
import pathlib
import sys


INTERVAL = "32"
ENTRYPOINT = "/work/input/proven_v0513_endpoint_entrypoint.py"


def install() -> None:
    # sitecustomize also runs in spawned children.  Only the admitted endpoint
    # launcher owns the server CLI; children receive the already parsed args.
    if not sys.argv or sys.argv[0] != ENTRYPOINT:
        return
    if "--stream-interval" in sys.argv:
        raise RuntimeError("residual intervention requires the bound default stream interval")
    sys.argv.extend(["--stream-interval", INTERVAL])
    audit = pathlib.Path(os.environ["RESIDUAL_CANDIDATE_AUDIT"])
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open("a") as handle:
        handle.write(
            json.dumps(
                {
                    "candidate_path": "ServerArgs.stream_interval -> OutputStreamer interval-gated publication",
                    "entrypoint": sys.argv[0],
                    "intervention": "stream_interval_32",
                    "new_stream_interval": int(INTERVAL),
                    "old_stream_interval": 1,
                    "pid": os.getpid(),
                    "source": "sglang/srt/managers/scheduler_components/output_streamer.py:326-342",
                },
                sort_keys=True,
            )
            + "\n"
        )
