"""`conversation_key(user_id, messages)`: how a conversation starts, as a key (PRD-013 Section 6.3, D2).

A versioned SHA-256 over the user id, the first `system` message (`""` when
there is none) and the first `user` message, framed as JSON the way
`dedup_key` frames its input, so content cannot forge a field boundary. A
`/v1` client resends its history on every request, so turn 1 and turn 50 of
one conversation carry the same key without a harness session.

Over raw text only: no redacted string is ever passed in (Section 9.2
invariants, the PRD-003 rule as PRD-010 extended it). Pure: no I/O, no
settings, no database. It reaches `app.db` only through `duplicate_checker`'s
own imports, to reuse `_sha256_json` rather than copy it.

A grouping aid, not an identity. Three documented limits:

1. Two conversations by the same user that start with the same `system`
   message and the same first `user` message share a key.
2. Every identical `/query` prompt by one user shares a key.
3. A client that compacts its context and rewrites its first user message
   starts a new key.

The chat UI's key can also change mid-session: once `chat_history.fit` drops
the first exchange, the first user message is a different one. For chat rows
`session_id` is the authoritative grouping.

Unlike `dedup_key`, the key is exposed on `/audit` and in the console (T13):
it hashes data the same reader already sees as `user_id` and the previews.
"""

from typing import Sequence

from app.models.messages import Message
# Bound by name, not read off the module: the `_sha256_json` spy in
# tests/test_query_pipeline_multiturn.py then sees only dedup_key's calls.
from app.services.duplicate_checker import _sha256_json

CONVERSATION_KEY_VERSION = "c1"


def conversation_key(user_id: str, messages: Sequence[Message]) -> str:
    first_system = next((m.content for m in messages if m.role == "system"), "")
    # No default: _validate_conversation (query_pipeline) runs first and
    # guarantees the last message is a user turn, so one always exists.
    first_user = next(m.content for m in messages if m.role == "user")
    return _sha256_json([CONVERSATION_KEY_VERSION, user_id, first_system, first_user])
