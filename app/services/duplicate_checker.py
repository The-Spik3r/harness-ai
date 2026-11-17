import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol, Sequence

from app.db import audit_journal
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

    # PRD-018 D12 (STORY-011 R1): the journal overlay is read BEFORE the lookup
    # and used only AFTER it succeeded and found nothing. Read after, a row the
    # drainer commits after the lookup's read and removes from the index before
    # ours would be invisible to both. The overlay never stands in for the
    # database: a failed lookup still fails closed below and discards it, and
    # a row the lookup found is the answer.
    journaled = audit_journal.pending_duplicate(user_id, key, cutoff)
    try:
        match = find_duplicate_timestamp(user_id, key, cutoff)
    except StorageError as exc:
        raise DuplicateCheckError(f"Duplicate lookup failed: {exc}") from exc

    if match is None:
        match = journaled
    if match is None:
        return DuplicateCheckResult(is_duplicate=False)
    return DuplicateCheckResult(is_duplicate=True, first_query_at=match)


class DedupTurn(Protocol):
    role: str
    content: str
    # Optional tool fields (`tool_calls`, `tool_call_id`) are read with getattr
    # (PRD-017 D5), so `Message` and any role/content object both satisfy this.


DEDUP_KEY_VERSION = "v1"
_KEYED_ROLES = frozenset({"system", "user", "assistant", "tool"})

# The anchor's slot in a tool-shaped prefix (PRD-017 Section 6.4). A tool-free
# prefix is a list of [role, content] pairs and never contains a bare null, so
# the two framings cannot collide.
_ANCHOR = None


def _sha256_json(value) -> str:
    framed = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(framed.encode("utf-8")).hexdigest()


def _frame(turn) -> list:
    """One non-anchor turn in a tool-shaped prefix (PRD-017 Section 6.4)."""
    if turn.role == "tool":
        return [turn.role, turn.content, getattr(turn, "tool_call_id", None)]
    calls = getattr(turn, "tool_calls", ())
    if calls:
        # arguments is the raw string, never parsed (PRD-017 D13).
        return [turn.role, turn.content, [[c.id, c.name, c.arguments] for c in calls]]
    return [turn.role, turn.content]


def _has_tool_fields(turns) -> bool:
    return any(t.role == "tool" or getattr(t, "tool_calls", ()) for t in turns)


def dedup_key(user_id: str, turns: Sequence[DedupTurn]) -> str:
    """Step 1's duplicate key over the whole conversation.

    PRD-009 Section 6.2 / D4 keyed system/user/assistant turns and left tool
    turns to "PRD-016" (this PRD). PRD-017 D4 / Section 6.4: with any tool turn
    or assistant tool_calls, the anchor is the last user turn, never a tool turn;
    the prefix holds every turn in order, the anchor's slot marked null, and
    each other turn framed as [role, content], [role, content, [[id, name,
    arguments], ...]] (assistant with calls) or [role, content, tool_call_id]
    (tool turn).

    Tool-free conversations take today's path, so their keys are byte-identical
    to PRD-009's and no 24-hour window resets (pinned in tests/test_dedup_key.py).

    Running `npm test` twice in one agent loop is not a duplicate: each loop
    request carries a longer prefix. A byte-identical resend is.
    """
    if not turns:
        raise ValueError("dedup_key needs at least one turn")
    if any(t.role not in _KEYED_ROLES for t in turns):
        raise ValueError("dedup_key has no rule for this role")
    if turns[-1].role not in ("user", "tool"):
        raise ValueError("dedup_key keys on a final user turn or a final tool turn")
    # user_id sits inside the key as well as in the lookup's WHERE clause: defence
    # in depth (PRD-009 Section 6.2), so a lookup that forgets the column still
    # cannot match across users. In the tool-free branch the last turn contributes
    # the prompt_hash value; for a tool-final conversation the audit prompt_hash is
    # the tool turn (PRD-017 D7) while the key's anchor is the last user turn (D4).
    if not _has_tool_fields(turns):
        *prefix, last = turns
        prefix_hash = "" if not prefix else _sha256_json([[t.role, t.content] for t in prefix])
        return _sha256_json([DEDUP_KEY_VERSION, user_id, hash_prompt(last.content), prefix_hash])
    anchor_index = None
    for i, t in enumerate(turns):
        if t.role == "user":
            anchor_index = i
    if anchor_index is None:
        raise ValueError("dedup_key needs a user turn to anchor on (PRD-017 D4)")
    prefix_hash = _sha256_json(
        [_ANCHOR if i == anchor_index else _frame(t) for i, t in enumerate(turns)]
    )
    return _sha256_json(
        [DEDUP_KEY_VERSION, user_id, hash_prompt(turns[anchor_index].content), prefix_hash]
    )
