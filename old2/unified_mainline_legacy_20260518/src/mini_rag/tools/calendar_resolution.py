from __future__ import annotations

# Compatibility shim. Calendar selector and write-target resolution are owned by
# the calendar capability layer; older imports keep working through this module.
from mini_rag.capabilities.calendar.resolver import *  # noqa: F401,F403
