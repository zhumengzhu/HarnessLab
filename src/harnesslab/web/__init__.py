"""Local Web UI for HarnessLab (Phase 3.2).

``harnesslab serve`` binds a localhost-only HTTP server that exposes
the same ``HarnessLoop`` and ``SessionStorePort`` as the CLI.
"""

from harnesslab.web.server import serve

__all__ = ["serve"]
