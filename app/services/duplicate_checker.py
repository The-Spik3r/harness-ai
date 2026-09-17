import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol, Sequence

from app.db.database import find_duplicate_timestamp
from app.db.errors import StorageError

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class DuplicateCheckError(Exception):
    pass


@dataclass
class DuplicateCheckResult:
    is_duplicate: bool
    first_query_at: Optional[str] = None


def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


# key is dedup_key(user_id, turns) (PRD-009 Section 6.2): hashing happens there,
# from raw text. Named key, not dedup_key, so it does not shadow that function.
def check_duplicate(user_id: str, key: str) -> DuplicateCheckResult:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(_TIMESTAMP_FORMAT)

    try:
        match = find_duplicate_timestamp(user_id, key, cutoff)
    except StorageError as exc:
        raise DuplicateCheckError(f"Duplicate lookup failed: {exc}") from exc

    if match is None:
        return DuplicateCheckResult(is_duplicate=False)
    return DuplicateCheckResult(is_duplicate=True, first_query_at=match)


class DedupTurn(Protocol):
    role: str
    content: str


DEDUP_KEY_VERSION = "v1"
_KEYED_ROLES = frozenset({"system", "user", "assistant"})


def _sha256_json(value) -> str:
    framed = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(framed.encode("utf-8")).hexdigest()


def dedup_key(user_id: str, turns: Sequence[DedupTurn]) -> str:
    if not turns:
        raise ValueError("dedup_key needs at least one turn")
    if any(t.role not in _KEYED_ROLES for t in turns):
        raise ValueError("dedup_key has no rule for this role (tool turns: PRD-016)")
    *prefix, last = turns
    if last.role != "user":
        raise ValueError("dedup_key keys on a final user turn")
    prefix_hash = "" if not prefix else _sha256_json([[t.role, t.content] for t in prefix])
    # user_id sits inside the key as well as in the lookup's WHERE clause: defence
    # in depth (PRD-009 Section 6.2), so a lookup that forgets the column still
    # cannot match across users. The last turn contributes the prompt_hash value.
    return _sha256_json([DEDUP_KEY_VERSION, user_id, hash_prompt(last.content), prefix_hash])
