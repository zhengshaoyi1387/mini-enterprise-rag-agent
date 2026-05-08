from __future__ import annotations

"""FastAPI dependencies for authentication and role extraction."""

from fastapi import Header, HTTPException, status

from mini_rag.config import Settings, get_settings
from mini_rag.security.permissions import normalize_role


def verify_api_key(x_api_key: str | None = Header(default=None)) -> bool:
    """Validate the caller's API key from the ``X-API-Key`` header.

    This is intentionally a minimal API-key mechanism, suitable for a small
    Agent Infra demo. Production systems would replace this with gateway auth,
    OAuth/JWT, mTLS, or an internal service identity.
    """

    settings: Settings = get_settings()
    expected = settings.agent_api_key
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AGENT_API_KEY is not configured on the server",
        )
    if x_api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return True


def get_request_role(x_user_role: str | None = Header(default="guest")) -> str:
    """Read caller role from header and normalize unknown values to guest."""

    return normalize_role(x_user_role)
