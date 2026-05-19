from __future__ import annotations

"""Compatibility shim for tool input gates.

The execution-layer implementation lives in ``mini_rag.execution.tool_input``.
Keep this module so older tests/imports continue to work while new code imports
from execution directly.
"""

from mini_rag.execution.tool_input import *  # noqa: F401,F403
