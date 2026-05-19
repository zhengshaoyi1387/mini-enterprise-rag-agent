from __future__ import annotations

# Compatibility shim. Date/time contract logic is owned by the datetime
# capability resolver; graph modules should import from that layer directly.
from mini_rag.capabilities.datetime.resolver import *  # noqa: F401,F403
