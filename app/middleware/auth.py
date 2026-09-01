import secrets
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.services.authz import PermissionDenied, authorize
from app.services.identity import Identity, resolve

_bearer_scheme = HTTPBearer(auto_error=False)


def require_identity(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Identity:
    identity = resolve(credentials.credentials if credentials else None)
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
