import hashlib
import secrets
from dataclasses import dataclass
from typing import Optional

from app.config import settings
from app.db.database import find_user_by_token_hash

# secrets.token_urlsafe(32) -> 256 bits of entropy, matching PRD Section 4.
_TOKEN_NBYTES = 32

# Synthetic identity for the ADMIN_TOKEN break-glass credential (PRD-001,
# retained by PRD-005 Section 4). It resolves without a row in `users` and
# without the database being reachable at all -- see Design Note 4.
_ADMIN_BREAK_GLASS_USER_ID = "admin"
_ADMIN_ROLE = "admin"


@dataclass(frozen=True)
class Identity:
    """The single currency of authorization in the system (PRD Section 4).

    Produced only by resolve() below -- nothing else in production code
    constructs one. Frozen so a role cannot be mutated after the point it
    was verified (PRD Risk 5).
    """

    user_id: str
    role: str


def hash_token(token: str) -> str:
    """SHA-256 digest of a credential. Deliberately independent of the
    prompt-hashing helper used for deduplication elsewhere in the codebase:
    same algorithm, different purpose -- see the story's Technical Notes."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token() -> str:
    """Generates a new credential. Returns the plaintext -- the caller is
    responsible for hashing it before persisting and for showing it to the
    operator exactly once (scripts/manage_users.py, STORY-004)."""
    return secrets.token_urlsafe(_TOKEN_NBYTES)


def resolve(token: Optional[str]) -> Optional[Identity]:
    """Verifies a credential and returns the Identity it belongs to, or
    None. None covers every failure case alike -- unknown, malformed,
    empty, or deactivated -- so the caller cannot distinguish them (PRD
    Section 9; STORY-002 Design Note 5 makes the same choice one layer
    down)."""
    if not token:
        return None

    if secrets.compare_digest(token, settings.ADMIN_TOKEN):
        return Identity(user_id=_ADMIN_BREAK_GLASS_USER_ID, role=_ADMIN_ROLE)

    user = find_user_by_token_hash(hash_token(token))
    if user is None:
        return None

    return Identity(user_id=user.user_id, role=user.role)
