"""Expose the pinned image's bundled cuSPARSE headers to the JIT compiler."""

import os
from pathlib import Path


_CUSPARSE_INCLUDE = Path("/usr/local/lib/python3.12/dist-packages/nvidia/cusparse/include")
if not (_CUSPARSE_INCLUDE / "cusparse.h").is_file():
    raise RuntimeError("pinned_image_cusparse_header_missing")
_existing = os.environ.get("CPLUS_INCLUDE_PATH")
os.environ["CPLUS_INCLUDE_PATH"] = (
    f"{_CUSPARSE_INCLUDE}:{_existing}" if _existing else str(_CUSPARSE_INCLUDE)
)
