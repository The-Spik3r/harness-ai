import secrets
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.db.errors import StorageUnavailableError
from app.services.authz import PermissionDenied, authorize
from app.services.identity import Identity, resolve
from app.services.storage_faults import STORAGE_UNAVAILABLE_DETAIL, retry_after_headers

_bearer_scheme = HTTPBearer(auto_error=False)


def require_identity(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Identity:
    try:
        identity = resolve(credentials.credentials if credentials else None)
    except StorageUnavailableError as exc:
        # PRD-018 D8, Section 9.1: a storage outage must not read as a bad
        # credential (PRD-007 STORY-004). Only the transient refusal is mapped:
        # any other storage failure stays a 500. Break-glass never reaches the
        # read, so it still resolves.
        raise HTTPException(
            status_code=503, detail=STORAGE_UNAVAILABLE_DETAIL, headers=retry_after_headers(exc)
        ) from exc
    if identity is None:
        raise HTTPException(status_code=401, detail="Invalid or missing credential")
    return identity


def require_permission(permission: str):
    def _require_permission(identity: Identity = Depends(require_identity)) -> Identity:
        try:
            authorize(identity, permission)
        except PermissionDenied:
            raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
        return identity

    return _require_permission


def require_admin_token(identity: Identity = Depends(require_identity)) -> None:
    if identity.role != "admin":
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")
