import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.db.database import find_duplicate_timestamp

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class DuplicateCheckError(Exception):
    pass


@dataclass
class DuplicateCheckResult:
    is_duplicate: bool
    first_query_at: Optional[str] = None


def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def check_duplicate(prompt: str) -> DuplicateCheckResult:
    prompt_hash = hash_prompt(prompt)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(_TIMESTAMP_FORMAT)

    try:
        match = find_duplicate_timestamp(prompt_hash, cutoff)
    except sqlite3.Error as exc:
        raise DuplicateCheckError(f"Duplicate lookup failed: {exc}") from exc

    if match is None:
        return DuplicateCheckResult(is_duplicate=False)
    return DuplicateCheckResult(is_duplicate=True, first_query_at=match)
