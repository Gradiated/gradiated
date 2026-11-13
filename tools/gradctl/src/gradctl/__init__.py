"""gradctl: the Gradiated developer and agent CLI. See tools/gradctl/README.md."""

VERSION = '0.1.0'

try:  # Written by build.py into the single-file build.
    from ._build import BUILD
except ImportError:
    BUILD = None
