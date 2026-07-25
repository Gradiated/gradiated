"""Optional scientific tools for production-shaped inference research.

These modules are deliberately independent of the lab scheduler. Researchers
may call their CLIs, import their small libraries, or bypass them when a
project-specific tool is a better fit.
"""

from .common import ScienceToolError

__all__ = ["ScienceToolError"]
